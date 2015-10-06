import base64
import string
import logging
import pylibmc
import time
import hashlib
import hmac
import simplejson as json
from dateutil import tz
from datetime import datetime, timedelta
from markupsafe import Markup
from random import choice
from urlparse import urlparse

from cgi import FieldStorage
from pyramid.settings import asbool
from pyramid.i18n import TranslationString
from pyramid.httpexceptions import HTTPFound

from boto.connection import AWSAuthConnection

from ..forms.login import EucaLogoutForm
from ..models.auth import EucaAuthenticator
from ..models.auth import ConnectionManager
from ..models import Notification
from . import boto_error_handler, JSONError
from ..caches import long_term
from ..caches import invalidate_cache
from ..i18n import _


class BaseView(object):
    """Base class for all views"""
    def __init__(self, request, **kwargs):
        self.request = request
        self.region = request.session.get('region')
        self.access_key = request.session.get('access_id')
        self.secret_key = request.session.get('secret_key')
        self.cloud_type = request.session.get('cloud_type')
        self.security_token = request.session.get('session_token')
        self.euca_logout_form = EucaLogoutForm(self.request)

    def get_connection(self, conn_type='ec2', cloud_type=None, region=None, access_key=None,
                       secret_key=None, security_token=None):
        conn = None
        if cloud_type is None:
            cloud_type = self.cloud_type

        if region is None:
            region = self.region
        if access_key is None:
            access_key = self.access_key
        if secret_key is None:
            secret_key = self.secret_key
        if security_token is None:
            security_token = self.security_token

        validate_certs = False
        if self.request.registry.settings:  # do this to pass tests
            validate_certs = asbool(self.request.registry.settings.get('connection.ssl.validation', False))
            certs_file = self.request.registry.settings.get('connection.ssl.certfile', None)
        if cloud_type == 'aws':
            conn = ConnectionManager.aws_connection(
                region, access_key, secret_key, security_token, conn_type, validate_certs)
        elif cloud_type == 'euca':
            host = self._get_ufs_host_setting_()
            port = self._get_ufs_port_setting_()
            dns_enabled = self.request.session.get('dns_enabled', True)
            conn = ConnectionManager.euca_connection(
                host, port, access_key, secret_key, security_token,
                conn_type, dns_enabled, validate_certs, certs_file
            )

        return conn

    def get_account_display_name(self):
        if self.cloud_type == 'euca':
            return self.request.session.get('account')
        return self.request.session.get('access_id')  # AWS

    def is_csrf_valid(self):
        return self.request.session.get_csrf_token() == self.request.params.get('csrf_token')

    def _store_file_(self, filename, mime_type, contents):
        # disable using memcache for file storage
        # try:
        #    default_term.set('file_cache', (filename, mime_type, contents))
        # except pylibmc.Error as ex:
        #    logging.warn("memcached misconfigured or not reachable, using session storage")
        # to re-enable, uncomment lines above and indent 2 lines below
        session = self.request.session
        session['file_cache'] = (filename, mime_type, contents)

    def _has_file_(self):
        # check both cache and session
        # disable using memcache for file storage
        # try:
        #    return not isinstance(default_term.get('file_cache'), NoValue)
        # except pylibmc.Error as ex:
        # to re-enable, uncomment lines above and indent 2 lines below
        session = self.request.session
        return 'file_cache' in session

    def get_user_data(self):
        input_type = self.request.params.get('inputtype')
        userdata_input = self.request.params.get('userdata')
        userdata_file_param = self.request.POST.get('userdata_file')
        userdata_file = userdata_file_param.file.read() if isinstance(userdata_file_param, FieldStorage) else None
        if input_type == 'file':
            userdata = userdata_file
        elif input_type == 'text':
            userdata = userdata_input
        else:
            userdata = userdata_file or userdata_input or None  # Look up file upload first
        return userdata

    def get_shared_buckets_storage_key(self, host):
        return "{0}{1}{2}{3}".format(
            host,
            self.region,
            self.request.session['account' if self.cloud_type == 'euca' else 'access_id'],
            self.request.session['username'] if self.cloud_type == 'euca' else '',
        )

    @long_term.cache_on_arguments(namespace='images')
    def _get_images_cached_(self, _owners, _executors, _ec2_region, acct, ufshost):
        """
        This method is decorated and will cache the image set
        """
        return self._get_images_(_owners, _executors, _ec2_region)

    def _get_images_(self, _owners, _executors, _ec2_region):
        """
        this method produces a cachable list of images
        """
        with boto_error_handler(self.request):
            logging.info("loading images from server (not cache)")
            filters = {'image-type': 'machine'}
            images = self.get_connection().get_all_images(owners=_owners, executable_by=_executors, filters=filters)
            ret = []
            for img in images:
                # trim some un-necessary items we don't need to cache
                del img.connection
                del img.region
                del img.product_codes
                del img.billing_products
                # alter things we want to cache, but are un-picklable
                if img.block_device_mapping:
                    for bdm in img.block_device_mapping.keys():
                        mapping_type = img.block_device_mapping[bdm]
                        del mapping_type.connection
                ret.append(img)
            return ret

    def get_images(self, conn, owners, executors, ec2_region):
        """
        This method sets the right account value so we cache private images per-acct
        and handles caching error by fetching the data from the server.
        """
        acct = self.request.session.get('account', '')
        if acct == '':
            acct = self.request.session.get('access_id', '')
        if 'amazon' in owners or 'aws-marketplace' in owners:
            acct = ''
        ufshost = self.get_connection().host if self.cloud_type == 'euca' else ''
        try:
            if self.cloud_type == 'euca' and asbool(self.request.registry.settings.get('cache.images.disable', False)):
                return self._get_images_(owners, executors, ec2_region)
            else:
                return self._get_images_cached_(owners, executors, ec2_region, acct, ufshost)
        except pylibmc.Error:
            logging.warn('memcached not responding')
            return self._get_images_(owners, executors, ec2_region)

    def invalidate_images_cache(self):
        region = self.request.session.get('region')
        acct = self.request.session.get('account', '')
        if acct == '':
            acct = self.request.session.get('access_id', '')
        invalidate_cache(long_term, 'images', None, [], [], region, acct)
        invalidate_cache(long_term, 'images', None, [u'self'], [], region, acct)
        invalidate_cache(long_term, 'images', None, [], [u'self'], region, acct)

    def get_euca_authenticator(self):
        """
        This method centralizes configuration of the EucaAuthenticator.
        """
        host = self._get_ufs_host_setting_()
        port = self._get_ufs_port_setting_()
        validate_certs = asbool(self.request.registry.settings.get('connection.ssl.validation', False))
        conn = AWSAuthConnection(None, aws_access_key_id='', aws_secret_access_key='')
        ca_certs_file = conn.ca_certificates_file
        conn = None
        ca_certs_file = self.request.registry.settings.get('connection.ssl.certfile', ca_certs_file)
        dns_enabled = self.request.session.get('dns_enabled', True)
        auth = EucaAuthenticator(host, port, dns_enabled, validate_certs=validate_certs, ca_certs=ca_certs_file)
        return auth

    def get_account_attributes(self, attribute_names=None):
        self.__init__(self.request)
        attribute_names = attribute_names or ['supported-platforms']
        conn = self.get_connection()
        if conn:
            with boto_error_handler(self.request):
                attributes = conn.describe_account_attributes(attribute_names=attribute_names)
                return attributes[0].attribute_values

    def _get_ufs_host_setting_(self):
        host = self.request.registry.settings.get('ufshost')
        if not host:
            host = self.request.registry.settings.get('clchost', 'localhost')
        return host

    def _get_ufs_port_setting_(self):
        port = self.request.registry.settings.get('ufsport')
        if not port:
            port = self.request.registry.settings.get('clcport', 8773)
        return int(port)

    @staticmethod
    def is_vpc_supported(request):
        return 'VPC' in request.session.get('supported_platforms', [])

    @staticmethod
    def escape_braces(s):
        if type(s) in [str, unicode] or isinstance(s, Markup) or isinstance(s, TranslationString):
            return s.replace('{{', '&#123;&#123;').replace('}}', '&#125;&#125;')

    @staticmethod
    def unescape_braces(s):
        if type(s) in [str, unicode] or isinstance(s, Markup) or isinstance(s, TranslationString):
            return s.replace('&#123;&#123;', '{{').replace('&#125;&#125;', '}}')

    @staticmethod
    def sanitize_url(url):
        default_path = '/'
        if not url:
            return default_path
        parsed_url = urlparse(url)
        scheme = parsed_url.scheme
        netloc = parsed_url.netloc
        if scheme:
            if not netloc:  # Prevent arbitrary redirects when url scheme has extra slash e.g. "http:///example.com"
                return default_path
            url = parsed_url.path
        return url or default_path

    @staticmethod
    def get_remote_addr(request):
        return request.environ.get('HTTP_X_FORWARDED_FOR', getattr(request, 'remote_addr', ''))

    @staticmethod
    def log_message(request, message, level='info'):
        prefix = ''
        cloud_type = request.session.get('cloud_type', 'euca')
        if cloud_type == 'euca':
            account = request.session.get('account', '')
            username = request.session.get('username', '')
            prefix = u'{0}/{1}@{2}'.format(account, username, BaseView.get_remote_addr(request))
        elif cloud_type == 'aws':
            account = request.session.get('username_label', '')
            region = request.session.get('region')
            prefix = u'{0}/{1}@{2}'.format(account, region, BaseView.get_remote_addr(request))
        log_message = u"{prefix} [{id}]: {msg}".format(prefix=prefix, id=request.id, msg=message)
        if level == 'info':
            logging.info(log_message)
        elif level == 'error':
            logging.error(log_message)
            # Very useful to use this when an error is logged and you need more details
            # import traceback; traceback.print_exc()

    def log_request(self, message):
        self.log_message(self.request, message)

    @staticmethod
    def handle_error(err=None, request=None, location=None, template=u"{0}"):
        status = getattr(err, 'status', None) or err.args[0] if err.args else ""
        message = template.format(err.reason)
        if err.error_message is not None:
            message = err.error_message
            if 'because of:' in message:
                message = message[message.index("because of:") + 11:]
            if 'RelatesTo Error:' in message:
                message = message[message.index("RelatesTo Error:") + 16:]
                # do we need this logic in the common code?? msg = err.message.split('remoteDevice')[0]
                # this logic found in volumes.js
        BaseView.log_message(request, message, level='error')
        perms_notice = _(u'You do not have the required permissions to perform this '
                         u'operation. Please retry the operation, and contact your cloud '
                         u'administrator to request an updated access policy if the problem persists.')
        if request.is_xhr:
            if err.code in ['AccessDenied', 'UnauthorizedOperation']:
                message = perms_notice
            raise JSONError(message=message, status=status or 403)
        if status == 403 or 'token has expired' in message:  # S3 token expiration responses return a 400 status
            if err.code in ['AccessDenied', 'UnauthorizedOperation'] and location is not None:
                request.session.flash(perms_notice, queue=Notification.ERROR)
                raise HTTPFound(location=location)

            notice = _(u'Your session has timed out. This may be due to inactivity, '
                       u'a policy that does not provide login permissions, or an unexpected error. '
                       u'Please log in again, and contact your cloud administrator if the problem persists.')
            request.session.flash(notice, queue=Notification.WARNING)
            raise HTTPFound(location=request.route_path('login'))
        request.session.flash(message, queue=Notification.ERROR)
        if location is None:
            location = request.current_route_url()
        raise HTTPFound(location)

    @staticmethod
    def escape_json(json_string):
        """Escape JSON strings passed to AngularJS controllers in templates"""
        replace_mapping = {
            "\'": "__apos__",
            '\\"': "__dquote__",
            "\\": "__bslash__",
        }
        for key, value in replace_mapping.items():
            json_string = json_string.replace(key, value)
        return json_string

    @staticmethod
    def dt_isoformat(dt_obj, tzone='UTC'):
        """Convert a timezone-unaware datetime object to tz-aware one and return it as an ISO-8601 formatted string"""
        return dt_obj.replace(tzinfo=tz.gettz(tzone)).isoformat()

    # these methods copied from euca2ools:bundleinstance.py and used with small changes
    @staticmethod
    def generate_default_policy(bucket, prefix, token=None):
        delta = timedelta(hours=24)
        expire_time = (datetime.utcnow() + delta).replace(microsecond=0)

        conditions = [{'acl': 'ec2-bundle-read'},
                      {'bucket': bucket},
                      ['starts-with', '$key', prefix]]
        if token is not None:
            conditions.append({'x-amz-security-token': token})
        policy = {'conditions': conditions,
                  'expiration': time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                              expire_time.timetuple())}
        policy_json = json.dumps(policy)
        return base64.b64encode(policy_json)

    @staticmethod
    def gen_policy_signature(policy, secret_key):
        # hmac cannot handle unicode
        secret_key = secret_key.encode('ascii', 'ignore')
        my_hmac = hmac.new(secret_key, digestmod=hashlib.sha1)
        my_hmac.update(policy)
        return base64.b64encode(my_hmac.digest())

    @staticmethod
    def has_role_access(request):
        return request.session['cloud_type'] == 'euca' and request.session['role_access']

    @staticmethod
    def generate_random_string(length=16):
        chars = string.letters + string.digits
        return ''.join(choice(chars) for i in range(length))

    @staticmethod
    def encode_unicode_dict(unicode_dict):
        encoded_dict = {}
        for k, v in unicode_dict.iteritems():
            if isinstance(k, unicode):
                k = k.encode('utf-8')
            elif isinstance(k, str):
                k.decode('utf-8')
            if isinstance(v, unicode):
                v = v.encode('utf-8')
            elif isinstance(v, str):
                v.decode('utf-8')
            encoded_dict[k] = v
        return encoded_dict

