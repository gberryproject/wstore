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

from __future__ import unicode_literals

import json
import logging
import rdflib
import re
import base64
import os
import traceback

from StringIO import StringIO
from datetime import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId
from urlparse import urlparse

from django.conf import settings
from django.template import loader
from django.template import Context as TmplContext
from django.core.exceptions import PermissionDenied

from wstore.repository_adaptor.repositoryAdaptor import RepositoryAdaptor
from wstore.market_adaptor.marketadaptor import MarketAdaptor
from wstore.search.search_engine import SearchEngine
from wstore.offerings.offering_rollback import OfferingRollback
from wstore.models import Offering, Repository, Resource
from wstore.models import Marketplace
from wstore.models import Purchase
from wstore.models import UserProfile, Context
from wstore.store_commons.utils.usdlParser import USDLParser, validate_usdl
from wstore.store_commons.utils.version import is_lower_version
from wstore.store_commons.utils.name import is_valid_id
from wstore.store_commons.utils.url import is_valid_url
from wstore.social.tagging.tag_manager import TagManager

logger = logging.getLogger('wstore.offerings.offerings_management')

####

def get_offering_info(offering, user):

    user_profile = UserProfile.objects.get(user=user)

    # Check if the user has purchased the offering
    state = offering.state

    # Check if the current organization is the user organization
    if user_profile.is_user_org():

        if offering.pk in user_profile.offerings_purchased:
            state = 'purchased'
            purchase = Purchase.objects.get(offering=offering, customer=user, organization_owned=False)

        if offering.pk in user_profile.rated_offerings:
            state = 'rated'

    else:
        if offering.pk in user_profile.current_organization.offerings_purchased:
            state = 'purchased'
            purchase = Purchase.objects.get(offering=offering, owner_organization=user_profile.current_organization)

        if user_profile.current_organization.has_rated_offering(user, offering):
            state = 'rated'

    # Load offering data
    result = {
        'name': offering.name,
        'owner_organization': offering.owner_organization.name,
        'owner_admin_user_id': offering.owner_admin_user.username,
        'version': offering.version,
        'state': state,
        'description_url': offering.description_url,
        'rating': "{:.2f}".format(offering.rating),
        'comments': offering.comments,
        'tags': offering.tags,
        'image_url': offering.image_url,
        'related_images': offering.related_images,
        'creation_date': str(offering.creation_date),
        'publication_date': str(offering.publication_date),
        'open': offering.open,
        'resources': []
    }

    # Load resources
    for res in offering.resources:
        resource = Resource.objects.get(pk=res)
        res_info = {
            'name': resource.name,
            'version': resource.version,
            'description': resource.description,
            'content_type': resource.content_type,
            'open': resource.open
        }

        if (state == 'purchased' or state == 'rated' or offering.open):
            if resource.resource_path != '':
                res_info['link'] = resource.resource_path
            elif resource.download_link != '':
                res_info['link'] = resource.download_link

        result['resources'].append(res_info)

    if settings.OILAUTH:
        result['applications'] = offering.applications

    # Load applications
    # Load offering description
    parser = USDLParser(json.dumps(offering.offering_description), 'application/json')
    result['offering_description'] = parser.parse()

    if not offering.open and (state == 'purchased' or state == 'rated'):
        result['bill'] = purchase.bill

        # If the offering has been purchased the parsed pricing model is replaced
        # With the pricing model of the contract in order to included the extra info
        # needed such as renovation dates etc.

        pricing_model = purchase.contract.pricing_model

        if 'subscription' in pricing_model:
            result['offering_description']['pricing']['price_plans'][0]['price_components'] = []
            # Cast renovation date to string in order to avoid serialization problems

            for subs in pricing_model['subscription']:
                subs['renovation_date'] = str(subs['renovation_date'])
                result['offering_description']['pricing']['price_plans'][0]['price_components'].append(subs)

            if 'single_payment' in pricing_model:
                result['offering_description']['pricing']['price_plans'][0]['price_components'].extend(pricing_model['single_payment'])

            if 'pay_per_use' in pricing_model:
                result['offering_description']['pricing']['price_plans'][0]['price_components'].extend(pricing_model['pay_per_use'])

    return result


def _get_purchased_offerings(user, db, pagination=None, sort=None):

    # Get the user profile purchased offerings
    user_profile = db.wstore_userprofile.find_one({'user_id': ObjectId(user.pk)})
    # Get the user organization purchased offerings
    organization = db.wstore_organization.find_one({'_id': user_profile['current_organization_id']})

    if not user.userprofile.is_user_org():
        user_purchased = organization['offerings_purchased']

    else:
        # If the current organization is the user organization, load
        # all user offerings

        user_purchased = user_profile['offerings_purchased']

        # Append user offerings from organization offerings
        for offer in organization['offerings_purchased']:
            if not offer in user_purchased:
                user_purchased.append(offer)

    # Check sorting

    if sort == 'creation_date':
        user_purchased = sorted(user_purchased, key=lambda off: Offering.objects.get(pk=off).creation_date, reverse=True)
    elif sort == 'publication_date':
        user_purchased = sorted(user_purchased, key=lambda off: Offering.objects.get(pk=off).publication_date, reverse=True)
    elif sort == 'name':
        user_purchased = sorted(user_purchased, key=lambda off: Offering.objects.get(pk=off).name)
    elif sort == 'rating':
        user_purchased = sorted(user_purchased, key=lambda off: Offering.objects.get(pk=off).rating, reverse=True)

    # If pagination has been defined take the offerings corresponding to the page
    if pagination:
        skip = int(pagination['skip']) - 1
        limit = int(pagination['limit'])

        if skip < len(user_purchased):
            user_purchased = user_purchased[skip:(skip + limit)]
        else:
            user_purchased = []

    return user_purchased


# Gets a set of offerings depending on filter value
def get_offerings(user, filter_='published', owned=False, pagination=None, sort=None):

    if pagination and (not int(pagination['skip']) > 0 or not int(pagination['limit']) > 0):
        raise Exception('Invalid pagination limits')

    # Set sorting values
    order = -1
    if sort == None or sort == 'date':
        if not owned and  filter_ == 'published':
            sorting = 'publication_date'
        else:
            sorting = 'creation_date'
    elif sort == 'popularity':
        sorting = 'rating'
    else:
        sorting = sort
        if sorting == 'name':
            order = 1

    # Get all the offerings owned by the provider using raw mongodb access
    connection = MongoClient()
    db = connection[settings.DATABASES['default']['NAME']]
    offerings = db.wstore_offering

    # Pagination: define the first element and the number of elements
    if owned and filter_ != 'purchased':
        current_organization = user.userprofile.current_organization
        query = {
            'owner_organization_id': ObjectId(current_organization.id)
        }

        if  filter_ == 'uploaded':
            query['state'] = 'uploaded'

        elif  filter_ == 'published':
            query['state'] = 'published'

        prov_offerings = offerings.find(query).sort(sorting, order)

    elif owned and filter_ == 'purchased':
        if pagination:
            prov_offerings = _get_purchased_offerings(user, db, pagination, sort=sorting)
            pagination = None
        else:
            prov_offerings = _get_purchased_offerings(user, db, sort=sorting)

    else:
        if  filter_ == 'published':
            prov_offerings = offerings.find({'state': 'published'}).sort(sorting, order)

    if pagination:
        prov_offerings = prov_offerings.skip(int(pagination['skip']) - 1).limit(int(pagination['limit']))

    result = []

    for offer in prov_offerings:
        if '_id' in offer:
            pk = str(offer['_id'])
        else:
            pk = offer

        offering = Offering.objects.get(pk=pk)
        # Use get_offering_info to create the JSON with the offering info
        result.append(get_offering_info(offering, user))

    return result


def count_offerings(user, filter_='published', owned=False):

    if owned:
        current_org = user.userprofile.current_organization

        # If the current organization is not the user organization
        # get only the offerings owned by that organization
        if  filter_ == 'uploaded' or filter_ == 'published':
            count = Offering.objects.filter(owner_admin_user=user, state=filter_, owner_organization=current_org).count()
        elif filter_ == 'all':
            count = Offering.objects.filter(owner_admin_user=user, owner_organization=current_org).count()
        elif filter_ == 'purchased':
            count = len(current_org.offerings_purchased)
            if user.userprofile.is_user_org():
                count += len(user.userprofile.offerings_purchased)
        else:
            raise ValueError('Filter not allowed')

    else:
        if  filter_ == 'published':
            count = Offering.objects.filter(state='published').count()
        else:
            raise ValueError('Filter not allowed')

    return {'number': count}


def _create_basic_usdl(usdl_info):

    # Get the template
    usdl_template = loader.get_template('usdl/usdl_template.rdf')
    # Create the context

    if usdl_info['base_uri'].endswith('/'):
        usdl_info['base_uri'] = usdl_info['base_uri'] + 'storeOfferingCollection/'
    else:
        usdl_info['base_uri'] = usdl_info['base_uri'] + '/storeOfferingCollection/'

    site = Context.objects.all()[0].site.domain

    if site.endswith('/'):
        site = site[:-1]

    image_url = site + usdl_info['image_url']

    free = False
    if usdl_info['pricing']['price_model'] == 'free':
        free = True

    context = {
        'base_uri': usdl_info['base_uri'],
        'name': usdl_info['name'],
        'fixed_name': usdl_info['name'].replace(' ', ''),
        'image_url': image_url,
        'description': usdl_info['description'],
        'created': str(datetime.now()),
        'free': free
    }

    if not free:
        context['price'] = usdl_info['pricing']['price']

    if 'legal' in usdl_info:
        context['legal'] = True
        context['legal_title'] = usdl_info['legal']['title']
        context['legal_text'] = usdl_info['legal']['text']

    # Render the template
    usdl = usdl_template.render(TmplContext(context))
    # Return the USDL document
    return usdl


def _validate_offering_info(offering_info):
    # Validate USDL mandatory fields
    if not 'description' in offering_info or not 'pricing' in offering_info:
        raise ValueError('Invalid USDL info: Missing a required field')

    # Validate that description field is not empty
    if not offering_info['description']:
        raise ValueError('Invalid USDL info: Description field cannot be empty')

    # Validate legal fields
    if 'legal' in offering_info:
        if not 'title' in offering_info['legal'] or not 'text' in offering_info['legal']:
            raise ValueError('Invalid USDL info: Title and text fields are required if providing legal info')

        if not offering_info['legal']['title'] or not offering_info['legal']['text']:
            raise ValueError('Invalid USDL info: Title and text fields cannot be empty in legal info')

    # Validate pricing fields
    if not 'price_model' in offering_info['pricing']:
        raise ValueError('Invalid USDL info: The pricing field must define a pricing model')

    if offering_info['pricing']['price_model'] != 'free' and offering_info['pricing']['price_model'] != 'single_payment':
        raise ValueError('Invalid USDL info: Invalid pricing model')

    if offering_info['pricing']['price_model'] == 'single_payment':
        if not 'price' in offering_info['pricing']:
            raise ValueError('Invalid USDL info: Missing price for single payment model')

        if not offering_info['pricing']['price']:
            raise ValueError('Invalid USDL info: Price cannot be empty in single payment models')


# Creates a new offering including the media files and
# the repository uploads
@OfferingRollback
def create_offering(provider, json_data):
    try: 
        logger.debug('create_offering()')
        profile = provider.userprofile
        data = {}
        if not 'name' in json_data or not 'version' in json_data:
            raise ValueError('Missing required fields')
    
        data['name'] = json_data['name']
        data['version'] = json_data['version']
    
        if not re.match(re.compile(r'^(?:[1-9]\d*\.|0\.)*(?:[1-9]\d*|0)$'), data['version']):
            raise ValueError('Invalid version format')
    
        if not is_valid_id(data['name']):
            raise ValueError('Invalid name format')
    
        # Get organization
        organization = profile.current_organization
        
        logger.debug('create_offering(): checking existing offerings')
        # Check if the offering already exists
        existing = True
    
        try:
            Offering.objects.get(name=data['name'], owner_organization=organization, version=data['version'])
        except:
            existing = False
    
        if existing:
            raise Exception('The offering already exists')
    
        # Check if the version of the offering is lower than an existing one
        offerings = Offering.objects.filter(owner_organization=organization, name=data['name'])
        for off in offerings:
            if is_lower_version(data['version'], off.version):
                raise ValueError('A bigger version of the current offering exists')
    
        is_open = json_data.get('open', False)
    
        logger.debug('create_offering(): before authentication')
        
        # If using the idm, get the applications from the request
        if settings.OILAUTH:
    
            # Validate application structure
            data['applications'] = []
    
            for app in json_data['applications']:
                data['applications'].append({
                    'name': app['name'],
                    'url': app['url'],
                    'id': app['id'],
                    'description': app['description']
                })
    
        data['related_images'] = []
        
        logger.debug('create_offering(): before notication URL')
        # Check the URL to notify the provider
        notification_url = ''
    
        if 'notification_url' in json_data:
            if json_data['notification_url'] == 'default':
                notification_url = organization.notification_url
                if not notification_url:
                    raise ValueError('There is not a default notification URL defined for the organization ' + organization.name + '. To configure a default notification URL provide it in the settings menu')
            else:
                # Check the notification URL
                if not is_valid_url(json_data['notification_url']):
                    raise ValueError("Invalid notification URL format: It doesn't seem to be an URL")
    
                notification_url = json_data['notification_url']
    
        logger.debug('create_offering(): create app media directory')
        # Create the directory for app media
        dir_name = organization.name + '__' + data['name'] + '__' + data['version']
        path = os.path.join(settings.MEDIA_ROOT, dir_name)
        os.makedirs(path)
    
        if not 'image' in json_data:
            raise ValueError('Missing required field: Logo')
    
        if not isinstance(json_data['image'], dict):
            raise TypeError('Invalid image type')
    
        logger.debug('create_offering(): image handling')
        
        image = json_data['image']
    
        if not 'name' in image or not 'data' in image:
            raise ValueError('Missing required field in image')
    
        # Save the application image or logo
        f = open(os.path.join(path, image['name']), "wb")
        dec = base64.b64decode(image['data'])
        f.write(dec)
        f.close()
    
        data['image_url'] = settings.MEDIA_URL + dir_name + '/' + image['name']
        # Save screen shots
        if 'related_images' in json_data:
            for image in json_data['related_images']:
    
                # images must be encoded in base64 format
                f = open(os.path.join(path, image['name']), "wb")
                dec = base64.b64decode(image['data'])
                f.write(dec)
                f.close()
    
                data['related_images'].append(settings.MEDIA_URL + dir_name + '/' + image['name'])
    
        # Save USDL document
        # If the USDL itself is provided
    
        if 'offering_description' in json_data:
            logger.debug('create_offering(): USDL upload')
            usdl_info = json_data['offering_description']
    
            repository = Repository.objects.get(name=json_data['repository'])
            repository_adaptor = RepositoryAdaptor(repository.host, 'storeOfferingCollection')
            offering_id = organization.name + '__' + data['name'] + '__' + data['version']
    
            usdl = usdl_info['data']
            data['description_url'] = repository_adaptor.upload(usdl_info['content_type'], usdl_info['data'], name=offering_id)
    
        # If the USDL is already uploaded in the repository
        elif 'description_url' in json_data:
            logger.debug('create_offering(): using url for USDL')
            
            # Check that the link to USDL is unique since could be used to
            # purchase offerings from Marketplace
            usdl_info = {}
            usdl_url = json_data['description_url']
            off = Offering.objects.filter(description_url=usdl_url)
    
            if len(off) != 0:
                raise ValueError('The provided USDL description is already registered')
    
            # Download the USDL from the repository
            repository_adaptor = RepositoryAdaptor(usdl_url)
            accept = "text/plain; application/rdf+xml; text/turtle; text/n3"
    
            usdl = repository_adaptor.download(content_type=accept)
            usdl_info['content_type'] = usdl['content_type']
    
            usdl = usdl['data']
            data['description_url'] = usdl_url
    
        # If the USDL is going to be created
        elif 'offering_info' in json_data:
            logger.debug('create_offering(): create basic USDL')
            
            _validate_offering_info(json_data['offering_info'])
    
            offering_info = json_data['offering_info']
            offering_info['image_url'] = data['image_url']
            offering_info['name'] = data['name']
    
            repository = Repository.objects.get(name=json_data['repository'])
    
            offering_info['base_uri'] = repository.host
    
            usdl = _create_basic_usdl(offering_info)
            usdl_info = {
                'content_type': 'application/rdf+xml'
            }
    
            repository_adaptor = RepositoryAdaptor(repository.host, 'storeOfferingCollection')
            offering_id = organization.name + '__' + data['name'] + '__' + data['version']
            data['description_url'] = repository_adaptor.upload(usdl_info['content_type'], usdl, name=offering_id)
        else:
            raise Exception('No USDL description provided')
    
        logger.debug('create_offering(): validating USDL')
        
        # Validate the USDL
        data['open'] = is_open
        data['organization'] = organization
        valid = validate_usdl(usdl, usdl_info['content_type'], data)
    
        if not valid[0]:
            raise Exception(valid[1])
    
        # Check new currencies used
        if len(valid) > 2:
            new_curr = valid[2]
    
            # Set the currency as used
            cont = Context.objects.all()[0]
            currency = None
            # Search the currency
            for c in cont.allowed_currencies['allowed']:
                if c['currency'].lower() == new_curr.lower():
                    currency = c
                    break
    
            cont.allowed_currencies['allowed'].remove(currency)
            currency['in_use'] = True
            cont.allowed_currencies['allowed'].append(currency)
            cont.save()
    
        # Serialize and store USDL info in json-ld format
        graph = rdflib.Graph()
        rdf_format = usdl_info['content_type']
    
        if rdf_format == 'text/turtle' or rdf_format == 'text/plain':
                rdf_format = 'n3'
        elif rdf_format == 'application/json':
                rdf_format = 'json-ld'
    
        graph.parse(data=usdl, format=rdf_format)
        data['offering_description'] = graph.serialize(format='json-ld', auto_compact=True)
    
        logger.debug('create_offering(): actual offering creation')
        # Create the offering
        offering = Offering.objects.create(
            name=data['name'],
            owner_organization=organization,
            owner_admin_user=provider,
            version=data['version'],
            state='uploaded',
            description_url=data['description_url'],
            resources=[],
            comments=[],
            tags=[],
            image_url=data['image_url'],
            related_images=data['related_images'],
            offering_description=json.loads(data['offering_description']),
            notification_url=notification_url,
            creation_date=datetime.now(),
            open=is_open
        )
    
        if settings.OILAUTH:
            offering.applications = data['applications']
            offering.save()
    
        if 'resources' in json_data and len(json_data['resources']) > 0:
            bind_resources(offering, json_data['resources'], profile.user)
    
        # Load offering document to the search index
        index_path = settings.DATADIR
        index_path = os.path.join(index_path, 'search')
        index_path = os.path.join(index_path, 'indexes')
    
        search_engine = SearchEngine(index_path)
        search_engine.create_index(offering)
        
    except Exception as e:
        uibuff = StringIO()
        traceback.print_exc()
        logger.error(uibuff.getvalue())
        raise e


def update_offering(offering, data):
    logger.debug('update_offering(): update offering')

    # Check if the offering has been published,
    # if published the offering cannot be updated
    if offering.state != 'uploaded' and not offering.open:
        raise PermissionDenied('The offering cannot be edited')

    dir_name = offering.owner_organization.name + '__' + offering.name + '__' + offering.version
    path = os.path.join(settings.MEDIA_ROOT, dir_name)

    # Update the logo
    if 'image' in data:
        # take just file name from url
        logo_file_name = os.path.basename(offering.image_url)
        logo_path = os.path.join(path, logo_file_name) 
        
        # Remove the old logo
        os.remove(logo_path)

        # Save the new logo
        f = open(os.path.join(path, data['image']['name']), "wb")
        dec = base64.b64decode(data['image']['data'])
        f.write(dec)
        f.close()
        offering.image_url = settings.MEDIA_URL + dir_name + '/' + data['image']['name']

    # Update the related images
    if 'related_images' in data:

        # Delete old related images
        for img in offering.related_images:
            old_image = os.path.join(settings.DATADIR, img[1:])
            os.remove(old_image)

        offering.related_images = []

        # Create new images
        for img in data['related_images']:
            f = open(os.path.join(path, img['name']), "wb")
            dec = base64.b64decode(img['data'])
            f.write(dec)
            f.close()
            offering.related_images.append(settings.MEDIA_URL + dir_name + '/' + img['name'])

    new_usdl = False
    
    logger.debug('update_offering(): images ok, checking offering_description')
    
    # Update the USDL description
    if 'offering_description' in data:
        logger.debug('update_offering(): upload USDL')
        usdl_info = data['offering_description']

        repository_adaptor = RepositoryAdaptor(offering.description_url)

        usdl = usdl_info['data']
        repository_adaptor.upload(usdl_info['content_type'], usdl)
        new_usdl = True

    # The USDL document has changed in the repository
    elif 'description_url' in data:
        logger.debug('update_offering(): USDL upload url')
        usdl_info = {}
        usdl_url = data['description_url']

        # Check the link
        if usdl_url != offering.description_url:
            raise ValueError('The provided USDL URL is not valid')

        # Download new content
        repository_adaptor = RepositoryAdaptor(usdl_url)
        accept = "text/plain; application/rdf+xml; text/turtle; text/n3"
        usdl = repository_adaptor.download(content_type=accept)

        usdl_info['content_type'] = usdl['content_type']
        usdl = usdl['data']

        new_usdl = True
    elif 'offering_info' in data:
        logger.debug('update_offering(): basic USDL')
        
        usdl_info = {
            'content_type': 'application/rdf+xml'
        }
        # Validate USDL info
        if not 'description' in data['offering_info'] or not 'pricing' in data['offering_info']:
            raise ValueError('Invalid USDL info')

        offering_info = data['offering_info']
        offering_info['image_url'] = offering.image_url

        offering_info['name'] = offering.name

        splited_desc_url = offering.description_url.split('/')

        base_uri = splited_desc_url[0] + '//'
        splited_desc_url.remove(splited_desc_url[0])
        splited_desc_url.remove(splited_desc_url[0])
        splited_desc_url.remove(splited_desc_url[-1])
        splited_desc_url.remove(splited_desc_url[-1])

        for p in splited_desc_url:
            base_uri += (p + '/')

        offering_info['base_uri'] = base_uri

        usdl = _create_basic_usdl(offering_info)
        usdl_info = {
            'content_type': 'application/rdf+xml'
        }

        repository_adaptor = RepositoryAdaptor(offering.description_url)
        repository_adaptor.upload(usdl_info['content_type'], usdl)
        new_usdl = True

    # If the USDL has changed store the new description
    # in the offering model
    if new_usdl:
        # Validate the USDL
        valid = validate_usdl(usdl, usdl_info['content_type'], {
            'name': offering.name,
            'organization': offering.owner_organization
        })

        if not valid[0]:
            raise ValueError(valid[1])

        # Serialize and store USDL info in json-ld format
        graph = rdflib.Graph()

        rdf_format = usdl_info['content_type']

        if usdl_info['content_type'] == 'text/turtle' or usdl_info['content_type'] == 'text/plain':
            rdf_format = 'n3'
        elif usdl_info['content_type'] == 'application/json':
            rdf_format = 'json-ld'

        off_description = usdl
        if rdf_format != 'json-ld':
            graph.parse(data=usdl, format=rdf_format)
            off_description = graph.serialize(format='json-ld', auto_compact=True)

        offering.offering_description = json.loads(off_description)

    offering.save()

    # Update offering indexes
    index_path = settings.DATADIR
    index_path = os.path.join(index_path, 'search')
    index_path = os.path.join(index_path, 'indexes')

    se = SearchEngine(index_path)
    se.update_index(offering)


def publish_offering(offering, data):

    # Validate data
    if not 'marketplaces' in data:
        raise ValueError('Publication error: missing required field, marketplaces')

    # Validate the state of the offering
    if not offering.state == 'uploaded':
        raise PermissionDenied('Publication error: The offering ' + offering.name + ' ' + offering.version +' cannot be published')

    # Validate the offering has enough content to be published
    # Open offerings cannot be published in they do not contain
    # digital assets (applications or resources)
    if offering.open and not len(offering.resources) and not len(offering.applications):
        raise PermissionDenied('Publication error: Open offerings cannot be published if they do not contain at least a digital asset (resource or application)')

    # Publish the offering in the selected marketplaces
    for market in data['marketplaces']:
        try:
            m = Marketplace.objects.get(name=market)
        except:
            raise ValueError('Publication error: The marketplace ' + market + ' does not exist')

        market_adaptor = MarketAdaptor(m.host)
        info = {
            'name': offering.name,
            'url': offering.description_url
        }
        market_adaptor.add_service(settings.STORE_NAME, info)
        offering.marketplaces.append(m.pk)

    offering.state = 'published'
    offering.publication_date = datetime.now()
    offering.save()

    # Update offering indexes
    index_path = settings.DATADIR
    index_path = os.path.join(index_path, 'search')
    index_path = os.path.join(index_path, 'indexes')

    se = SearchEngine(index_path)
    se.update_index(offering)


def _remove_offering(offering, se):
    # If the offering has media files delete them
    dir_name = offering.owner_organization.name + '__' + offering.name + '__' + offering.version
    path = os.path.join(settings.MEDIA_ROOT, dir_name)

    try:
        files = os.listdir(path)

        for f in files:
            file_path = os.path.join(path, f)
            os.remove(file_path)

        os.rmdir(path)
    except OSError as e:
        # An OS error means that offering files
        # does not exist so continue with the deletion
        pass

    # Remove the search index
    se.remove_index(offering)

    # Remove the offering ID from the tag indexes
    if len(offering.tags):
        tm = TagManager()
        tm.delete_tag(offering)

    # Remove the offering pk from the bound resources
    for res in offering.resources:
        resource = Resource.objects.get(pk=unicode(res))
        resource.offerings.remove(offering.pk)
        resource.save()

    offering.delete()

def delete_offering(offering):
    # If the offering has been purchased it is not deleted
    # it is marked as deleted in order to allow customers that
    # have purchased the offering to install it if needed

    #delete the usdl description from the repository
    if offering.state == 'deleted':
        raise PermissionDenied('The offering is already deleted')

    parsed_url = urlparse(offering.description_url)
    path = parsed_url.path
    host = parsed_url.scheme + '://' + parsed_url.netloc
    path = path.split('/')
    host += '/' + path[1] + '/' + path[2]
    collection = path[3]

    repository_adaptor = RepositoryAdaptor(host, collection)
    repository_adaptor.delete(path[4])

    index_path = settings.DATADIR
    index_path = os.path.join(index_path, 'search')
    index_path = os.path.join(index_path, 'indexes')

    se = SearchEngine(index_path)

    if offering.state == 'uploaded':
        _remove_offering(offering, se)
    else:
        offering.state = 'deleted'
        offering.save()

        # Delete the offering from marketplaces
        for market in offering.marketplaces:
            m = Marketplace.objects.get(pk=market)
            market_adaptor = MarketAdaptor(m.host)
            market_adaptor.delete_service(settings.STORE_NAME, offering.name)

        # Update offering indexes
        if not offering.open:
            se.update_index(offering)

        context = Context.objects.all()[0]
        # Check if the offering is in the newest list
        if offering.pk in context.newest:
            # Remove the offering from the newest list
            newest = context.newest

            if len(newest) < 8:
                newest.remove(offering.pk)
            else:
                # Get the 8 newest offerings using the publication date for sorting
                connection = MongoClient()
                db = connection[settings.DATABASES['default']['NAME']]
                offerings = db.wstore_offering
                newest_off = offerings.find({'state': 'published'}).sort('publication_date', -1).limit(8)

                newest = []
                for n in newest_off:
                    newest.append(str(n['_id']))

            context.newest = newest
            context.save()

        # Check if the offering is in the top rated list
        if offering.pk in context.top_rated:
            # Remove the offering from the top rated list
            top_rated = context.top_rated
            if len(top_rated) < 8:
                top_rated.remove(offering.pk)
            else:
                # Get the 4 top rated offerings
                connection = MongoClient()
                db = connection[settings.DATABASES['default']['NAME']]
                offerings = db.wstore_offering
                top_off = offerings.find({'state': 'published', 'rating': {'$gt': 0}}).sort('rating', -1).limit(8)

                top_rated = []
                for t in top_off:
                    top_rated.append(str(t['_id']))

            context.top_rated = top_rated
            context.save()

        if offering.open:
            _remove_offering(offering, se)


def bind_resources(offering, data, provider):
    logger.debug('bind_resources()')
    # Check that the offering supports binding
    if offering.state != 'uploaded' and not offering.open:
        raise PermissionDenied('This offering cannot be modified')

    added_resources = []
    offering_resources = []
    for of_res in offering.resources:
        offering_resources.append(of_res)

    logger.debug('bind_resources(): iterating resources')
    for res in data:
        try:
            logger.debug("bind_resources(): getting resource object: %s" % res['name'])
            resource = Resource.objects.get(name=res['name'], version=res['version'], provider=provider.userprofile.current_organization)
        except:
            raise ValueError('Resource not found: ' + res['name'] + ' ' + res['version'])
        
        # Check resource state
        if resource.state == 'deleted':
            raise PermissionDenied('Invalid resource, the resource ' + res['name'] + ' ' + res['version'] + ' is deleted')

        # Check open
        if not resource.open and offering.open:
            raise PermissionDenied('It is not allowed to include not open resources in an open offering')

        if not ObjectId(resource.pk) in offering_resources:
            added_resources.append(resource.pk)
        else:
            offering_resources.remove(ObjectId(resource.pk))

    # added_resources contains the resources to be added to the offering
    # and offering_resources the resources to be deleted from the offering
    logger.debug('bind_resources(): saving resources')
    for add_res in added_resources:
        resource = Resource.objects.get(pk=add_res)
        resource.offerings.append(offering.pk)
        resource.save()
        offering.resources.append(ObjectId(add_res))

    for del_res in offering_resources:
        resource = Resource.objects.get(pk=del_res)
        resource.offerings.remove(offering.pk)
        resource.save()
        offering.resources.remove(del_res)

    logger.debug('bind_resources(): saving offering')
    offering.save()
