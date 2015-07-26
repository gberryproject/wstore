# -*- coding: utf-8 -*-

# Copyright (c) 2013 CoNWeT Lab., Universidad Politécnica de Madrid

# This file is part of WStore.

# WStore is free software: you can redistribute it and/or modify
# it under the terms of the European Union Public Licence (EUPL)
# as published by the European Commission, either version 1.1
# of the License, or (at your option) any later version.

# WStore is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# European Union Public Licence for more details.

# You should have received a copy of the European Union Public Licence
# along with WStore.
# If not, see <https://joinup.ec.europa.eu/software/page/eupl/licence-eupl>.

import logging
import traceback
import sys

from StringIO import StringIO
            
from django.contrib.auth import get_user
from django.utils.importlib import import_module
from django.utils.functional import SimpleLazyObject
from django.utils.http import http_date, parse_http_date_safe

logger = logging.getLogger('wstore.middleware')

class URLMiddleware(object):

    _middleware = {}

    def load_middleware(self, group):
        """
        Populate middleware lists from settings.URL_MIDDLEWARE_CLASSES.
        """
        from django.conf import settings
        from django.core import exceptions

        middleware = {
            'process_request': [],
            'process_view': [],
            'process_template_response': [],
            'process_response': [],
            'process_exception': [],
        }
        for middleware_path in settings.URL_MIDDLEWARE_CLASSES[group]:
            try:
                mw_module, mw_classname = middleware_path.rsplit('.', 1)
            except ValueError:
                raise exceptions.ImproperlyConfigured('%s isn\'t a middleware module' % middleware_path)
            try:
                mod = import_module(mw_module)
            except ImportError, e:
                raise exceptions.ImproperlyConfigured('Error importing middleware %s: "%s"' % (mw_module, e))
            try:
                mw_class = getattr(mod, mw_classname)
            except AttributeError:
                raise exceptions.ImproperlyConfigured('Middleware module "%s" does not define a "%s" class' % (mw_module, mw_classname))
            try:
                mw_instance = mw_class()
            except exceptions.MiddlewareNotUsed:
                continue

            if hasattr(mw_instance, 'process_request'):
                middleware['process_request'].append(mw_instance.process_request)
            if hasattr(mw_instance, 'process_view'):
                middleware['process_view'].append(mw_instance.process_view)
            if hasattr(mw_instance, 'process_template_response'):
                middleware['process_template_response'].insert(0, mw_instance.process_template_response)
            if hasattr(mw_instance, 'process_response'):
                middleware['process_response'].insert(0, mw_instance.process_response)
            if hasattr(mw_instance, 'process_exception'):
                middleware['process_exception'].insert(0, mw_instance.process_exception)

        # We only assign to this when initialization is complete as it is used
        # as a flag for initialization being complete.
        self._middleware[group] = middleware

    def get_matched_middleware(self, path, middleware_method):

        # NOTE: sub url setup needs to taken into account here (/store part)
        if path.startswith('/store/api/'):
            group = 'api'
        elif path.startswith('/store/media/'):
            group = 'media'
        else:
            group = 'default'

        if group not in self._middleware:
            self.load_middleware(group)

        return self._middleware[group][middleware_method]

    def process_request(self, request):
        matched_middleware = self.get_matched_middleware(request.path, 'process_request')
        for middleware in matched_middleware:
            response = middleware(request)
            if response:
                return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        matched_middleware = self.get_matched_middleware(request.path, 'process_view')
        for middleware in matched_middleware:
            response = middleware(request, view_func, view_args, view_kwargs)
            if response:
                return response

    def process_template_response(self, request, response):
        matched_middleware = self.get_matched_middleware(request.path, 'process_template_response')
        for middleware in matched_middleware:
            response = middleware(request, response)
        return response

    def process_response(self, request, response):
        matched_middleware = self.get_matched_middleware(request.path, 'process_response')
        for middleware in matched_middleware:
            response = middleware(request, response)
        return response

    def process_exception(self, request, exception):
        matched_middleware = self.get_matched_middleware(request.path, 'process_exception')
        for middleware in matched_middleware:
            response = middleware(request, exception)
            if response:
                return response


def get_api_user(request):

    import json
    import urllib2
    from django.conf import settings
    from wstore.oauth2provider.models import Token
    from django.contrib.auth.models import User, AnonymousUser
    from wstore.social_auth_backend import FIWARE_USER_DATA_URL, fill_internal_user_info, FiwareBackend
    from wstore.store_commons.utils.method_request import MethodRequest

    # Get access_token from the request
    try:
        token = request.META['HTTP_AUTHORIZATION'].split(' ', 1)[1]
    except:
        return AnonymousUser()

    # If using the idM to authenticate users, validate the token

    if settings.OILAUTH:
        opener = urllib2.build_opener()
        url = FIWARE_USER_DATA_URL + '?access_token=' + token
        request = MethodRequest('GET', url)

        try:
            new_user = False
            response = opener.open(request)
            user_info = json.loads(response.read())
            # Try to get an internal user
            try:
                user = User.objects.get(username=user_info['nickName'])
            except:
                # The user is valid but she has never accessed wstore so
                # internal models should be created
                from social_auth.backends.pipeline.user import get_username
                from social_auth.backends.pipeline.user import create_user
                from social_auth.backends.pipeline.social import associate_user
                from social_auth.backends.pipeline.social import load_extra_data

                # The request is from a new user
                new_user = True

                # Get the internal username to be used
                details = {
                    'username': user_info['nickName'],
                    'email': user_info['email'],
                    'fullname': user_info['displayName']
                }
                username = get_username(details)

                # Create user structure
                auth_user = create_user('', details, '', user_info['actorId'], username['username'])

                # associate user with social user
                social_user = associate_user(FiwareBackend, auth_user['user'], user_info['actorId'])

                # Load  user extra data
                request = {
                    'access_token': token
                }
                load_extra_data(FiwareBackend, details, request, user_info['actorId'], social_user['user'], social_user=social_user['social_user'])

                # Refresh user info
                user = User.objects.get(username=user_info['nickName'])

            # If it is a new user the auth info contained in the userprofile is not valid
            if not new_user:
                # The user has been validated but the user info is not valid since the
                # used token belongs to an external application

                # Get FiPay token for the user
                # TeroV: this token might be empty if auth via store web UI has failed
                token = user.userprofile.access_token

                def refreshToken(user):
                    # The access token may expired, try to refresh it
                    social = user.social_auth.filter(provider='fiware')[0]
                    
                    result = social.refresh_token()
                    
                    # Try to get user info with the new access token
                    social = user.social_auth.filter(provider='fiware')[0]
                    new_credentials = social.extra_data

                    user.userprofile.access_token = new_credentials['access_token']
                    user.userprofile.refresh_token = new_credentials['refresh_token']
                    user.userprofile.save()

                    token = user.userprofile.access_token
                    url = FIWARE_USER_DATA_URL + '?access_token=' + token
                    request = MethodRequest('GET', url)
                    response = opener.open(request)
                    user_info = json.loads(response.read())
                    
                    user_info['access_token'] = token
                    user_info['refresh_token'] = user.userprofile.refresh_token
                    fill_internal_user_info((), response=user_info, user=user)
                
                # To get clear reason for unclear situation
                if token is None:
                    logger.debug("Token is empty")
                    # TODO: this is not correct action, because if no original login then we don't have refresh_token either
                    refreshToken(user)
                    
                else:
                    # try to use found token
                    try:
                        # Get valid user info for Fipay
                        url = FIWARE_USER_DATA_URL + '?access_token=' + token
                        request = MethodRequest('GET', url)
                        response = opener.open(request)
                        user_info = json.loads(response.read())
                        
                    except Exception, e:
                        logger.debug("Exception when calling IdM: %s" % str(e))
                        
                        if e.code == 401:
                            # server responded that code is not valid
                            logger.debug("Token was not valid -> refresh")
                            refreshToken(user)
                        else:
                            raise(e)

        except Exception, e:
            io = StringIO()
            traceback.print_exc(io)
            logger.error("User authentication failed. Returning AnonymousUser: %s" % io.getvalue())
            
            user = AnonymousUser()
            
    else: # Non OILAUTH case
        try:
            user = Token.objects.get(token=token).user
        except:
            user = AnonymousUser()

    return user


class AuthenticationMiddleware(object):

    def process_request(self, request):

        if 'HTTP_AUTHORIZATION' in request.META:
            request.user = SimpleLazyObject(lambda: get_api_user(request))
        else:
            request.user = SimpleLazyObject(lambda: get_user(request))


class ConditionalGetMiddleware(object):
    """
    Handles conditional GET operations. If the response has a ETag or
    Last-Modified header, and the request has If-None-Match or
    If-Modified-Since, the response is replaced by an HttpNotModified.

    Also sets the Date and Content-Length response-headers.
    """
    def process_response(self, request, response):
        response['Date'] = http_date()
        if not response.has_header('Content-Length'):
            response['Content-Length'] = str(len(response.content))

        if response.has_header('ETag'):
            if_none_match = request.META.get('HTTP_IF_NONE_MATCH')
            if if_none_match == response['ETag']:
                # Setting the status is enough here. The response handling path
                # automatically removes content for this status code (in
                # http.conditional_content_removal()).
                response.status_code = 304

        if response.has_header('Last-Modified'):
            if_modified_since = request.META.get('HTTP_IF_MODIFIED_SINCE')
            if if_modified_since is not None:
                try:
                    # IE adds a length attribute to the If-Modified-Since header
                    separator = if_modified_since.index(';')
                    if_modified_since = if_modified_since[0:separator]
                except:
                    pass
                if_modified_since = parse_http_date_safe(if_modified_since)
            if if_modified_since is not None:
                last_modified = parse_http_date_safe(response['Last-Modified'])
                if last_modified is not None and last_modified <= if_modified_since:
                    # Setting the status code is enough here (same reasons as
                    # above).
                    response.status_code = 304

        return response
