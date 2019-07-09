import mock
import pytest

from nose.tools import assert_equal

from addons.forward.tests.utils import ForwardAddonTestCase
from tests.base import OsfTestCase
from website import settings
from tests.json_api_test_app import JSONAPITestApp

pytestmark = pytest.mark.django_db

class TestForward(ForwardAddonTestCase, OsfTestCase):

    django_app = JSONAPITestApp()

    def setUp(self):
        super(TestForward, self).setUp()
        self.app.authenticate(*self.user.auth)

    def test_change_url_log_added(self):
        log_count = self.project.logs.count()
        self.app.put_json(
            self.project.api_url_for('forward_config_put'),
            dict(
                url='http://how.to.bas/ic',
            ),
        )
        self.project.reload()
        assert_equal(
            self.project.logs.count(),
            log_count + 1
        )

    @mock.patch.object(settings, 'SPAM_CHECK_ENABLED', True)
    @mock.patch('osf.models.node.Node.do_check_spam')
    def test_change_url_check_spam_v1(self, mock_check_spam):
        self.project.is_public = True
        self.project.save()
        self.app.put_json(self.project.api_url_for('forward_config_put'), {'url': 'http://possiblyspam.com'})

        assert mock_check_spam.called
        data, _ = mock_check_spam.call_args
        author, author_email, content, request_headers = data

        assert author == self.user.fullname
        assert author_email == self.user.username
        assert content == 'http://possiblyspam.com'

    @mock.patch.object(settings, 'SPAM_CHECK_ENABLED', True)
    @mock.patch('osf.models.node.Node.do_check_spam')
    def test_change_url_check_spam_v2(self, mock_check_spam):
        self.project.is_public = True
        self.project.save()
        self.django_app.put_json_api('/v2/nodes/{}/addons/forward/'.format(self.project._id),
                                     {'data': {'attributes': {'url': 'http://possiblyspam.com'}}},
                                     auth=self.user.auth)

        assert mock_check_spam.called
        data, _ = mock_check_spam.call_args
        author, author_email, content, request_headers = data

        assert author == self.user.fullname
        assert author_email == self.user.username
        assert content == 'http://possiblyspam.com'

    def test_change_timeout_log_not_added(self):
        log_count = self.project.logs.count()
        self.app.put_json(
            self.project.api_url_for('forward_config_put'),
            dict(
                url=self.node_settings.url,
            ),
        )
        self.project.reload()
        assert_equal(
            self.project.logs.count(),
            log_count
        )
