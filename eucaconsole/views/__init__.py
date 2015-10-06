# -*- coding: utf-8 -*-
# Copyright 2013-2015 Hewlett Packard Enterprise Development LP
#
# Redistribution and use of this software in source and binary forms,
# with or without modification, are permitted provided that the following
# conditions are met:
#
# Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
Core views

"""
import simplejson as json
import textwrap
import threading

from contextlib import contextmanager
from markupsafe import Markup
from urllib import urlencode
try:
    import python_magic as magic
except ImportError:
    import magic

from boto.ec2.blockdevicemapping import BlockDeviceType, BlockDeviceMapping
from boto.exception import BotoServerError

from pyramid.httpexceptions import HTTPException, HTTPUnprocessableEntity
from pyramid.i18n import TranslationString
from pyramid.response import Response
from pyramid.security import NO_PERMISSION_REQUIRED
from pyramid.view import notfound_view_config, view_config

from ..constants.images import AWS_IMAGE_OWNER_ALIAS_CHOICES, EUCA_IMAGE_OWNER_ALIAS_CHOICES
from ..i18n import _

from base import BaseView


def escape_braces(event):
    """Escape double curly braces in template variables to prevent AngularJS expression injections"""
    for k, v in event.rendering_val.items():
        if not k.endswith('_json'):
            if type(v) in [str, unicode] or isinstance(v, Markup) or isinstance(v, TranslationString):
                event.rendering_val[k] = BaseView.escape_braces(v)


class JSONResponse(Response):
    def __init__(self, status=200, message=None, id=None, **kwargs):
        super(JSONResponse, self).__init__(**kwargs)
        self.status = status
        self.content_type = 'application/json'
        self.body = json.dumps(
            dict(message=message, id=id)
        )


# Can use this for 1.5, but the fix below for 1.4 also works in 1.5.
# class JSONError(HTTPException):
class JSONError(HTTPUnprocessableEntity):
    def __init__(self, status=400, message=None, **kwargs):
        super(JSONError, self).__init__(**kwargs)
        self.status = status
        self.content_type = 'application/json'
        self.body = json.dumps(
            dict(message=message)
        )



class TaggedItemView(BaseView):
    """Common view for items that have tags (e.g. security group)"""

    def __init__(self, request, **kwargs):
        super(TaggedItemView, self).__init__(request, **kwargs)
        self.tagged_obj = None
        self.conn = None

    def add_tags(self):
        if self.conn:
            tags_json = self.request.params.get('tags')
            tags_dict = json.loads(tags_json) if tags_json else {}
            tags = {}
            for key, value in tags_dict.items():
                key = self.unescape_braces(key.strip())
                if not any([key.startswith('aws:'), key.startswith('euca:')]):
                    tags[key] = self.unescape_braces(value.strip())
            if tags:
                self.conn.create_tags([self.tagged_obj.id], tags)

    def remove_tags(self):
        if self.conn:
            tagkeys = []
            object_tags = self.tagged_obj.tags.keys()
            for tagkey in object_tags:
                if not any([tagkey.startswith('aws:'), tagkey.startswith('euca:')]):
                    tagkeys.append(tagkey)
            self.conn.delete_tags([self.tagged_obj.id], tagkeys)

    def update_tags(self):
        if self.tagged_obj is not None:
            self.remove_tags()
            self.add_tags()

    def update_name_tag(self, value):
        if self.tagged_obj is not None:
            if value != self.tagged_obj.tags.get('Name'):
                self.tagged_obj.remove_tag('Name')
                if value and not value.startswith('aws:'):
                    tag_value = self.unescape_braces(value)
                    self.tagged_obj.add_tag('Name', tag_value)

    @staticmethod
    def get_display_name(resource, escapebraces=True):
        name = ''
        if resource:
            name_tag = resource.tags.get('Name', '')
            name = u"{0}{1}".format(
                name_tag if name_tag else resource.id,
                u" ({0})".format(resource.id) if name_tag else ''
            )
        if escapebraces:
            name = BaseView.escape_braces(name)
        return name

    @staticmethod
    def get_tags_display(tags, skip_name=True, wrap_width=0):
        """Return comma-separated list of tags as a string.
           Skips the 'Name' tag by default. no wrapping by default, otherwise honor wrap_width"""
        tags_array = []
        for key, val in tags.items():
            if not any([key.startswith('aws:'), key.startswith('euca:')]):
                template = u'{0}={1}'
                if skip_name and key == 'Name':
                    continue
                else:
                    text = template.format(key, val)
                    if wrap_width > 0:
                        if len(text) > wrap_width:
                            tags_array.append(textwrap.fill(text, wrap_width))
                        else:
                            tags_array.append(text)
                    else:
                        tags_array.append(text)
        return ', '.join(tags_array)


class BlockDeviceMappingItemView(BaseView):
    def __init__(self, request):
        super(BlockDeviceMappingItemView, self).__init__(request)
        self.conn = self.get_connection()
        self.request = request

    def get_image(self):
        from eucaconsole.views.images import ImageView
        image_id = self.request.params.get('image_id')
        if self.conn and image_id:
            with boto_error_handler(self.request):
                image = self.conn.get_image(image_id)
                if image:
                    platform = ImageView.get_platform(image)
                    image.platform_name = ImageView.get_platform_name(platform)
                return image
        return None

    def get_owner_choices(self):
        if self.cloud_type == 'aws':
            return AWS_IMAGE_OWNER_ALIAS_CHOICES
        return EUCA_IMAGE_OWNER_ALIAS_CHOICES

    def get_snapshot_choices(self):
        choices = [('', _(u'None'))]
        for snapshot in self.conn.get_all_snapshots(owner='self'):
            value = snapshot.id
            snapshot_name = snapshot.tags.get('Name')
            label = u'{id}{name} ({size} GB)'.format(
                id=snapshot.id,
                name=u' - {0}'.format(snapshot_name) if snapshot_name else '',
                size=snapshot.volume_size
            )
            choices.append((value, label))
        return sorted(choices)

    @staticmethod
    def get_block_device_map(bdmapping_json=None):
        """Parse block_device_mapping JSON and return a configured BlockDeviceMapping object
        Mapping JSON structure...
            {"/dev/sda":
                {"snapshot_id": "snap-23E93E09", "volume_type": null, "delete_on_termination": true, "size": 1}  }
        """
        if bdmapping_json:
            mapping = json.loads(bdmapping_json)
            if mapping:
                bdm = BlockDeviceMapping()
                for key, val in mapping.items():
                    device = BlockDeviceType()
                    if val.get('virtual_name') is not None and val.get('virtual_name').startswith('ephemeral'):
                        device.ephemeral_name = val.get('virtual_name')
                    else:
                        device.volume_type = 'standard'
                        device.snapshot_id = val.get('snapshot_id') or None
                        device.size = val.get('size')
                        device.delete_on_termination = val.get('delete_on_termination', False)
                    bdm[key] = device
                return bdm
            return None
        return None


class LandingPageView(BaseView):
    """Common view for landing pages

    :ivar filter_keys: List of strings to pass to client-side filtering engine
        The search box input (usually above the landing page datagrid) will match each property in the list against
        each item in the collection to do the filtering.  See $scope.searchFilterItems in landingpage.js
    :ivar sort_keys: List of strings to pass to client-side sorting engine
        The sorting dropdown (usually above the landing page datagrid) will display a sorting option for
        each item in the list.  See templates/macros.pt (id="sorting_controls")
    :ivar initial_sort_key: The initial sort key used for Angular-based client-side sorting.
        Prefix the key with a '-' to perform a descending sort (e.g. '-launch_time')
    :ivar items: The list of dicts to pass to the JSON renderer to display the collection of items.
    :ivar prefix: The prefix for each landing page, relevant to the section
        For example, prefix = '/instances' for Instances

    """
    def __init__(self, request, **kwargs):
        super(LandingPageView, self).__init__(request, **kwargs)
        self.filter_keys = []
        self.sort_keys = []
        self.initial_sort_key = ''
        self.items = []
        self.prefix = '/'

    def filter_items(self, items, ignore=None, autoscale=False):
        ignore = ignore or []  # Pass list of filters to ignore
        ignore.append('csrf_token')
        filtered_items = []
        if hasattr(self.request.params, 'dict_of_lists'):
            filter_params = self.request.params.dict_of_lists()
            for skip in ignore:
                if skip in filter_params.keys():
                    del filter_params[skip]
            if not filter_params:
                return items
            for item in items:
                matchedkey_count = 0
                for filter_key, filter_value in filter_params.items():
                    if filter_value and filter_value[0]:
                        if filter_key == 'tags':  # Special case to handle tags
                            if self.match_tags(item=item, tags=filter_value[0].split(','), autoscale=autoscale):
                                matchedkey_count += 1
                        elif hasattr(item, filter_key):
                            filterkey_val = getattr(item, filter_key, None)
                            if filterkey_val:
                                if isinstance(filterkey_val, list):
                                    for fitem in filterkey_val:
                                        if fitem in filter_value:
                                            matchedkey_count += 1
                                else:
                                    if filterkey_val in filter_value:
                                        matchedkey_count += 1
                            elif 'none' in filter_value or 'None' in filter_value:
                                # Handle the special case where 'filterkey_val' value is None
                                if filterkey_val is None:
                                    matchedkey_count += 1
                    else:
                        matchedkey_count += 1  # Handle empty param values
                if matchedkey_count == len(filter_params):
                    filtered_items.append(item)
        return filtered_items

    def match_tags(self, item=None, tags=None, autoscale=False):
        for tag in tags:
            tag = self.unescape_braces(tag.strip())
            if autoscale:  # autoscaling tags are a list of Tag boto.ec2.autoscale.tag.Tag objects
                if item.tags:
                    for as_tag in item.tags:
                        if as_tag and tag == as_tag.key or tag == as_tag.value:
                            return True
            else:  # Standard tags are a dict of key/value pairs
                if any([tag in item.tags.keys(), tag in item.tags.values()]):
                    return True
        return False

    def get_json_endpoint(self, route, path=False):
        encoded_params = self.encode_unicode_dict(self.request.params)
        return u'{0}{1}'.format(
            self.request.route_path(route) if path is False else route,
            u'?{0}'.format(urlencode(encoded_params)) if self.request.params else ''
        )

    def get_redirect_location(self, route):
        location = u'{0}'.format(self.request.route_path(route))
        encoded_get_params = self.encode_unicode_dict(self.request.GET)
        if self.request.GET:
            location = u'{0}?{1}'.format(location, urlencode(encoded_get_params))
        return location


@notfound_view_config(renderer='../templates/notfound.pt')
def notfound_view(request):
    """404 Not Found view"""
    return dict()


@view_config(context=BotoServerError, permission=NO_PERMISSION_REQUIRED)
def conn_error(exc, request):
    """Generic handler for BotoServerError exceptions"""
    try:
        BaseView.handle_error(err=exc, request=request)
    except HTTPException as ex:
        return ex
    return


@contextmanager
def boto_error_handler(request, location=None, template="{0}"):
    try:
        yield
    except BotoServerError as err:
        BaseView.handle_error(err=err, request=request, location=location, template=template)


@view_config(route_name='file_download', request_method='POST')
def file_download(request):
    session = request.session
    if session.get('file_cache'):
        (filename, mime_type, contents) = session['file_cache']
        # Clean the session information regrading the new keypair
        del session['file_cache']
        response = Response(content_type=mime_type)
        response.body = str(contents)
        response.content_disposition = 'attachment; filename="{name}"'.format(name=filename)
        return response
    # no file found ...
    # this isn't handled on on client anyway, so we can return pretty much anything
    return Response(body='BaseView:file not found', status=500)

_magic_type = magic.Magic(mime=True)
_magic_type._thread_check = lambda: None
_magic_desc = magic.Magic(mime=False)
_magic_desc._thread_check = lambda: None
_magic_lock = threading.Lock()


def guess_mimetype_from_buffer(buffer, mime=False):
    with _magic_lock:
        if mime:
            return _magic_type.from_buffer(buffer)
        else:
            return _magic_desc.from_buffer(buffer)
