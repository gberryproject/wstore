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

# NOTE: This file is meant for case where WStore is configured to use suburl.
#       This means application is located for example in /store/ instead of /

from django.conf.urls.defaults import patterns, include, url
from django.contrib import admin

import wstore.urls
import wstore.registration.urls as registration
from wstore.views import ServeMedia

from django.views.generic import RedirectView
from django.core.urlresolvers import reverse_lazy

admin.autodiscover()

urlpatterns = patterns('',
    #url(r'^$', RedirectView.as_view(url=reverse_lazy('store'))),
    url(r'^store/admin/', include(admin.site.urls)),
    url(r'^store/login/?$', 'django.contrib.auth.views.login', name='login'),
    url(r'^store/logout/?$', 'wstore.store_commons.authentication.logout', name='logout'),
    url(r'^store/media/(?P<path>.+)/(?P<name>[\w -.]+)/?$', ServeMedia(permitted_methods=('GET',))),
    url('^store/', include(wstore.urls.urlpatterns)),
    url('^store/', include(registration.urlpatterns)),
)

#urlpatterns += wstore.urls.urlpatterns
#urlpatterns += registration.urlpatterns
