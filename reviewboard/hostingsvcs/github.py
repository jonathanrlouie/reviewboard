import hashlib
import hmac
from django.http import HttpResponse, HttpResponseBadRequest
from django.template import RequestContext
from django.template.loader import render_to_string
from django.utils.six.moves.urllib.parse import urljoin
from reviewboard.admin.server import build_server_url, get_server_url
                                                get_repository_for_hook,
                                                get_review_request_id)
    def api_get(self, url, *args, **kwargs):
            return data
                      'This code will be sent to you by GitHub.'))
                raise AuthorizationError(rsp['message'])
            raise HostingServiceError(rsp['message'])
            raise HostingServiceError(six.text_type(e))
class GitHub(HostingService):
    has_repository_hook_instructions = True

            'reviewboard.hostingsvcs.github.post_receive_hook_close_submitted',
            name='github-hooks-close-submitted')
    RAW_MIMETYPE = 'application/vnd.github.v3.raw'

    REFNAME_PREFIX = 'refs/heads/'
    REFNAME_PREFIX_LEN = len(REFNAME_PREFIX)

            repo_info = self._api_get_repository(
                self._get_repository_owner_raw(plan, kwargs),
                self._get_repository_name_raw(plan, kwargs))
        except Exception as e:
            if six.text_type(e) == 'Not Found':
                    # If we get a Not Found, then the authorization was
                    if six.text_type(e) != 'Not Found':
        url = self._build_api_url(self._get_repo_api_url(repository),
                                  'git/blobs/%s' % revision)

        try:
            return self.client.http_get(url, headers={
                'Accept': self.RAW_MIMETYPE,
            })[0]
        except (URLError, HTTPError):
            raise FileNotFoundError(path, revision)
        url = self._build_api_url(self._get_repo_api_url(repository),
                                  'git/blobs/%s' % revision)

            self.client.http_get(url, headers={
                'Accept': self.RAW_MIMETYPE,
            })

        except (URLError, HTTPError):

        url = self._build_api_url(self._get_repo_api_url(repository),
                                  'git/refs/heads')

        try:
            rsp = self.client.api_get(url)
        except Exception as e:
            logging.warning('Failed to fetch commits from %s: %s',
                            url, e)
            return results

        for ref in rsp:
            refname = ref['ref']

            if refname.startswith(self.REFNAME_PREFIX):
                name = refname[self.REFNAME_PREFIX_LEN:]
                results.append(Branch(id=name,
                                      commit=ref['object']['sha'],
                                      default=(name == 'master')))

        resource = 'commits'
        url = self._build_api_url(self._get_repo_api_url(repository), resource)

        if start:
            url += '&sha=%s' % start

        try:
            rsp = self.client.api_get(url)
        except Exception as e:
            logging.warning('Failed to fetch commits from %s: %s',
                            url, e)
            return results

        for item in rsp:
            url = self._build_api_url(repo_api_url, 'commits')
            url += '&sha=%s' % revision

            try:
                commit = self.client.api_get(url)[0]
            except Exception as e:
                raise SCMError(six.text_type(e))
        # Step 2: fetch the "compare two commits" API to get the diff if the
        # commit has a parent commit. Otherwise, fetch the commit itself.
        if parent_revision:
            url = self._build_api_url(
                repo_api_url, 'compare/%s...%s' % (parent_revision, revision))
        else:
            url = self._build_api_url(repo_api_url, 'commits/%s' % revision)

        try:
            comparison = self.client.api_get(url)
        except Exception as e:
            raise SCMError(six.text_type(e))

        if parent_revision:
            tree_sha = comparison['base_commit']['commit']['tree']['sha']
        else:
            tree_sha = comparison['commit']['tree']['sha']

        files = comparison['files']
        url = self._build_api_url(repo_api_url, 'git/trees/%s' % tree_sha)
        url += '&recursive=1'
        tree = self.client.api_get(url)
    def get_repository_hook_instructions(self, request, repository):
        """Returns instructions for setting up incoming webhooks."""
        plan = repository.extra_data['repository_plan']
        add_webhook_url = urljoin(
            self.account.hosting_url or 'https://github.com/',
            '%s/%s/settings/hooks/new'
            % (self._get_repository_owner_raw(plan, repository.extra_data),
               self._get_repository_name_raw(plan, repository.extra_data)))

        webhook_endpoint_url = build_server_url(local_site_reverse(
            'github-hooks-close-submitted',
            local_site=repository.local_site,
            kwargs={
                'repository_id': repository.pk,
                'hosting_service_id': repository.hosting_account.service_name,
            }))

        return render_to_string(
            'hostingsvcs/github/repo_hook_instructions.html',
            RequestContext(request, {
                'repository': repository,
                'server_url': get_server_url(),
                'add_webhook_url': add_webhook_url,
                'webhook_endpoint_url': webhook_endpoint_url,
                'hook_uuid': repository.get_or_create_hooks_uuid(),
            }))
        return '%s?access_token=%s' % (
            '/'.join(api_paths),
            self.account.data['authorization']['token'])
    def _api_get_repository(self, owner, repo_name):
        return self.client.api_get(self._build_api_url(
            self._get_repo_api_url_raw(owner, repo_name)))

def post_receive_hook_close_submitted(request, local_site_name=None,
                                      repository_id=None,
                                      hosting_service_id=None):
    hook_event = request.META.get('HTTP_X_GITHUB_EVENT')

    if hook_event == 'ping':
        # GitHub is checking that this hook is valid, so accept the request
        # and return.
        return HttpResponse()
    elif hook_event != 'push':
        return HttpResponseBadRequest(
            'Only "ping" and "push" events are supported.')

    repository = get_repository_for_hook(repository_id, hosting_service_id,
                                         local_site_name)

    # Validate the hook against the stored UUID.
    m = hmac.new(bytes(repository.get_or_create_hooks_uuid()), request.body,
                 hashlib.sha1)

    sig_parts = request.META.get('HTTP_X_HUB_SIGNATURE').split('=')

    if sig_parts[0] != 'sha1' or len(sig_parts) != 2:
        # We don't know what this is.
        return HttpResponseBadRequest('Unsupported HTTP_X_HUB_SIGNATURE')

    if m.hexdigest() != sig_parts[1]:
        return HttpResponseBadRequest('Bad signature.')

        return HttpResponseBadRequest('Invalid payload format')
    server_url = get_server_url(request=request)
    review_request_id_to_commits = \
        _get_review_request_id_to_commits_map(payload, server_url)
    if review_request_id_to_commits:
        close_all_review_requests(review_request_id_to_commits,
                                  local_site_name, repository,
                                  hosting_service_id)
def _get_review_request_id_to_commits_map(payload, server_url):
    review_request_id_to_commits_map = defaultdict(list)
        review_request_id_to_commits_map[review_request_id].append(
            '%s (%s)' % (branch_name, commit_hash[:7]))
    return review_request_id_to_commits_map