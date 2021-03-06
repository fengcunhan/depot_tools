# Copyright 2013 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from recipe_engine import recipe_api

class GerritApi(recipe_api.RecipeApi):
  """Module for interact with gerrit endpoints"""

  def __call__(self, name, cmd, infra_step=True, **kwargs):
    """Wrapper for easy calling of gerrit_utils steps."""
    assert isinstance(cmd, (list, tuple))
    prefix = 'gerrit '

    env = self.m.context.env
    env.setdefault('PATH', '%(PATH)s')
    env['PATH'] = self.m.path.pathsep.join([
        env['PATH'], str(self._module.PACKAGE_REPO_ROOT)])

    with self.m.context(env=env):
      return self.m.python(prefix + name,
                           self.package_repo_resource('gerrit_client.py'),
                           cmd,
                           infra_step=infra_step,
                           **kwargs)

  def create_gerrit_branch(self, host, project, branch, commit, **kwargs):
    """
    Create a new branch from given project and commit

    Returns:
      the ref of the branch created
    """
    args = [
        'branch',
        '--host', host,
        '--project', project,
        '--branch', branch,
        '--commit', commit,
        '--json_file', self.m.json.output()
    ]
    step_name = 'create_gerrit_branch'
    step_result = self(step_name, args, **kwargs)
    ref = step_result.json.output.get('ref')
    return ref

  # TODO(machenbach): Rename to get_revision? And maybe above to
  # create_ref?
  def get_gerrit_branch(self, host, project, branch, **kwargs):
    """
    Get a branch from given project and commit

    Returns:
      the revision of the branch
    """
    args = [
        'branchinfo',
        '--host', host,
        '--project', project,
        '--branch', branch,
        '--json_file', self.m.json.output()
    ]
    step_name='get_gerrit_branch'
    step_result = self(step_name, args, **kwargs)
    revision = step_result.json.output.get('revision')
    return revision

  def get_change_destination_branch(self, host, change, **kwargs):
    """
    Get the upstream branch for a given CL.

    Args:
      host: Gerrit host to query.
      change: The change number.

    Returns:
      the name of the branch
    """
    assert int(change)
    kwargs.setdefault('name', 'get_change_destination_branch')
    changes = self.get_changes(
        host,
        [('change', change)],
        limit=1,
        **kwargs
    )
    if not changes or 'branch' not in changes[0]:
      self.m.step.active_result.presentation.status = self.m.step.EXCEPTION
      raise self.m.step.InfraFailure(
          'Error quering for branch of CL %s' % change)
    return changes[0]['branch']

  def get_change_description(self, host, change, patchset):
    """
    Get the description for a given CL and patchset.

    Args:
      host: Gerrit host to query.
      change: The change number.
      patchset: The patchset number.

    Returns:
      The description corresponding to given CL and patchset.
    """
    assert int(change), change
    assert int(patchset), patchset
    cls = self.get_changes(
        host,
        query_params=[('change', str(change))],
        o_params=['ALL_REVISIONS', 'ALL_COMMITS'],
        limit=1)
    cl = cls[0] if len(cls) == 1 else {'revisions': {}}
    for ri in cl['revisions'].itervalues():
      # TODO(tandrii): add support for patchset=='current'.
      if str(ri['_number']) == str(patchset):
        return ri['commit']['message']

    raise self.m.step.InfraFailure(
        'Error querying for CL description: host:%r change:%r; patchset:%r' % (
            host, change, patchset))

  def get_changes(self, host, query_params, start=None, limit=None,
                  o_params=None, **kwargs):
    """
    Query changes for the given host.

    Args:
      host: Gerrit host to query.
      query_params: Query parameters as list of (key, value) tuples to form a
          query as documented here:
          https://gerrit-review.googlesource.com/Documentation/user-search.html#search-operators
      start: How many changes to skip (starting with the most recent).
      limit: Maximum number of results to return.
      o_params: A list of additional output specifiers, as documented here:
          https://gerrit-review.googlesource.com/Documentation/rest-api-changes.html#list-changes
    Returns:
      A list of change dicts as documented here:
          https://gerrit-review.googlesource.com/Documentation/rest-api-changes.html#list-changes
    """
    args = [
        'changes',
        '--host', host,
        '--json_file', self.m.json.output()
    ]
    if start:
      args += ['--start', str(start)]
    if limit:
      args += ['--limit', str(limit)]
    for k, v in query_params:
      args += ['-p', '%s=%s' % (k, v)]
    for v in (o_params or []):
      args += ['-o', v]

    return self(
        kwargs.pop('name', 'changes'),
        args,
        step_test_data=lambda: self.test_api.get_one_change_response_data(),
        **kwargs
    ).json.output
