import re
import sre_constants

from django import forms
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.utils.translation import ugettext as _

from reviewboard.diffviewer.forms import UploadDiffForm, EmptyDiffError
from reviewboard.reviews.errors import OwnershipError
from reviewboard.reviews.models import DefaultReviewer, ReviewRequest, \
                                       ReviewRequestDraft, Screenshot
from reviewboard.scmtools.errors import SCMError, ChangeNumberInUseError, \
                                        InvalidChangeNumberError, \
                                        ChangeSetError
from reviewboard.scmtools.models import Repository


class DefaultReviewerForm(forms.ModelForm):
    name = forms.CharField(
        label=_("Name"),
        max_length=64,
        widget=forms.TextInput(attrs={'size': '30'}))

    file_regex = forms.CharField(
        label=_("File regular expression"),
        max_length=256,
        widget=forms.TextInput(attrs={'size': '60'}),
        help_text=_('File paths are matched against this regular expression '
                    'to determine if these reviewers should be added.'))

    repository = forms.ModelMultipleChoiceField(
        label=_('Repositories'),
        required=False,
        queryset=Repository.objects.filter(visible=True).order_by('name'),
        help_text=_('The list of repositories to specifically match this '
                    'default reviewer for. If left empty, this will match '
                    'all repositories.'),
        widget=FilteredSelectMultiple(_("Repositories"), False))

    def clean_file_regex(self):
        """Validates that the specified regular expression is valid."""
        file_regex = self.cleaned_data['file_regex']

        try:
            re.compile(file_regex)
        except Exception, e:
            raise forms.ValidationError(e)

        return file_regex

    class Meta:
        model = DefaultReviewer


class NewReviewRequestForm(forms.Form):
    """
    A form that handles creationg of new review requests. These take
    information on the diffs, the repository the diffs are against, and
    optionally a changelist number (for use in certain repository types
    such as Perforce).
    """
    basedir = forms.CharField(
        label=_("Base Directory"),
        required=False,
        help_text=_("The absolute path in the repository the diff was "
                    "generated in."),
        widget=forms.TextInput(attrs={'size': '35'}))
    diff_path = forms.FileField(
        label=_("Diff"),
        required=True,
        help_text=_("The new diff to upload."),
        widget=forms.FileInput(attrs={'size': '35'}))
    parent_diff_path = forms.FileField(
        label=_("Parent Diff"),
        required=False,
        help_text=_("An optional diff that the main diff is based on. "
                    "This is usually used for distributed revision control "
                    "systems (Git, Mercurial, etc.)."),
        widget=forms.FileInput(attrs={'size': '35'}))
    repository = forms.ModelChoiceField(
        label=_("Repository"),
        queryset=Repository.objects.filter(visible=True).order_by('name'),
        empty_label=None,
        required=True)

    changenum = forms.IntegerField(label=_("Change Number"), required=False)

    @staticmethod
    def create_from_list(data, constructor, error):
        """Helper function to combine the common bits of clean_target_people
           and clean_target_groups"""
        names = [x for x in map(str.strip, re.split(',\s*', data)) if x]
        return set([constructor(name) for name in names])

    def create(self, user, diff_file, parent_diff_file):
        repository = self.cleaned_data['repository']
        changenum = self.cleaned_data['changenum'] or None

        # It's a little odd to validate this here, but we want to have access to
        # the user.
        if changenum:
            try:
                changeset = repository.get_scmtool().get_changeset(changenum)
            except NotImplementedError:
                # This scmtool doesn't have changesets
                pass
            except SCMError, e:
                self.errors['changenum'] = forms.util.ErrorList([str(e)])
                raise ChangeSetError()
            except ChangeSetError, e:
                self.errors['changenum'] = forms.util.ErrorList([str(e)])
                raise e

            if not changeset:
                self.errors['changenum'] = forms.util.ErrorList([
                    'This change number does not represent a valid '
                    'changeset.'])
                raise InvalidChangeNumberError()

            if user.username != changeset.username:
                self.errors['changenum'] = forms.util.ErrorList([
                    'This change number is owned by another user.'])
                raise OwnershipError()

        try:
            review_request = ReviewRequest.objects.create(user, repository,
                                                          changenum)
        except ChangeNumberInUseError:
            # The user is updating an existing review request, rather than
            # creating a new one.
            review_request = ReviewRequest.objects.get(changenum=changenum)
            review_request.update_from_changenum(changenum)

            if review_request.status == 'D':
                # Act like we're creating a brand new review request if the
                # old one is discarded.
                review_request.status = 'P'
                review_request.public = False

            review_request.save()

        diff_form = UploadDiffForm(repository, data={
            'basedir': self.cleaned_data['basedir'],
        },
        files={
            'path': diff_file,
            'parent_diff_path': parent_diff_file,
        })
        diff_form.full_clean()

        class SavedError(Exception):
            """Empty exception class for when we already saved the error info"""
            pass

        try:
            diff_form.create(diff_file, parent_diff_file,
                             review_request.diffset_history)
            if 'path' in diff_form.errors:
                self.errors['diff_path'] = diff_form.errors['path']
                raise SavedError
            elif 'base_diff_path' in diff_form.errors:
                self.errors['base_diff_path'] = diff_form.errors['base_diff_path']
                raise SavedError
        except SavedError:
            review_request.delete()
            raise
        except EmptyDiffError:
            review_request.delete()
            self.errors['diff_path'] = forms.util.ErrorList([
                'The selected file does not appear to be a diff.'])
            raise
        except Exception, e:
            review_request.delete()
            self.errors['diff_path'] = forms.util.ErrorList([e])
            raise

        review_request.add_default_reviewers()
        review_request.save()
        return review_request


class UploadScreenshotForm(forms.Form):
    """
    A form that handles uploading of new screenshots.
    A screenshot takes a path argument and optionally a caption.
    """
    caption = forms.CharField(required=False)
    path = forms.ImageField(required=True)

    def create(self, file, review_request):
        screenshot = Screenshot(caption=self.cleaned_data['caption'],
                                draft_caption=self.cleaned_data['caption'])
        screenshot.image.save(file.name, file, save=True)

        review_request.screenshots.add(screenshot)

        draft = ReviewRequestDraft.create(review_request)
        draft.screenshots.add(screenshot)
        draft.save()

        return screenshot
