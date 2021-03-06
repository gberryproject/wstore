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

from __future__ import absolute_import

import os
import json
import rdflib
from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId
from mock import MagicMock

from django.test import TestCase
from django.conf import settings
from django.contrib.auth.models import User
from django.test.utils import override_settings

from wstore.charging_engine import charging_engine
from wstore.models import Purchase
from wstore.models import UserProfile
from wstore.models import Organization
from wstore.charging_engine.management.commands import resolve_use_charging


__test__ = False

def fake_renovation_date(unit):

    if unit == 'per month':
        return datetime(2013, 04, 01, 00, 00, 00)
    elif unit == 'per week':
        return datetime(2013, 03, 20, 00, 00, 00)


class FakeClient():

    def __init__(self, purchase):
        pass

    def start_redirection_payment(self, price, currency):
        pass

    def end_redirection_payment(self, token, payer_id):
        pass

    def direct_payment(self, currency, price, credit_card):
        pass

    def get_checkout_url(self):
        return 'https://www.sandbox.paypal.com/webscr?cmd=_express-checkout&token=11111111'


class FakeThreading():

    class Timer():

        def __init__(self, time, handler):
            pass

        def start(self):
            pass


class FakeChargingEngine():

    _purchase = None
    _payment_method = None
    _credit_card = None

    def __init__(self, purchase, payment_method, credit_card):
        self._purchase = purchase
        self._payment_method = payment_method
        self._credit_card = credit_card

    def resolve_charging(self, sdr=False):

        if sdr and self._payment_method == 'credit_card':
            sdrs = self._purchase.contract.pending_sdrs
            self._purchase.contract.pending_sdrs = []
            self._purchase.contract.applied_sdrs.extend(sdrs)
            self._purchase.contract.save()


def fake_cdr_generation(parts, time):
    pass


class FakeSubprocess():

    def __init__(self):
        pass

    def call(self, prams):
        pass

class SinglePaymentChargingTestCase(TestCase):

    tags = ('fiware-ut-12',)
    fixtures = ['single_payment.json']

    _to_delete = []

    @classmethod
    def setUpClass(cls):
        reload(charging_engine)
        cls._auth = settings.OILAUTH
        charging_engine.subprocess = FakeSubprocess()
        settings.OILAUTH = False
        settings.PAYMENT_CLIENT = 'wstore.charging_engine.tests.FakeClient'
        super(SinglePaymentChargingTestCase, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        settings.OILAUTH = cls._auth
        super(SinglePaymentChargingTestCase, cls).tearDownClass()

    def test_basic_charging_single_payment(self):

        # Load model
        model = os.path.join(settings.BASEDIR, 'wstore')
        model = os.path.join(model, 'charging_engine')
        model = os.path.join(model, 'test')
        model = os.path.join(model, 'basic_price.ttl')
        f = open(model, 'rb')
        graph = rdflib.Graph()
        graph.parse(data=f.read(), format='n3')
        f.close()

        user = User.objects.get(pk='51070aba8e05cc2115f022f9')
        profile = UserProfile.objects.get(user=user)

        tax_address = {
            "street": "test street",
            "postal": "20000",
            "city": "test city",
            "country": "test country"
        }

        profile.tax_address = tax_address
        org = Organization.objects.get(pk='91000aba8e06ac2115f022f0')
        profile.organization = org
        profile.save()

        purchase = Purchase.objects.get(pk='61005aba8e05ac2115f022f0')

        offering = purchase.offering
        json_model = graph.serialize(format='json-ld', auto_compact=True)

        offering.offering_description = json.loads(json_model)
        offering.save()

        credit_card = {
            'type': 'Visa',
            'number': '1234123412341234',
            'expire_year': '2018',
            'expire_month': '2',
            'cvv2': '111',
        }

        purchase = Purchase.objects.get(pk='61005aba8e05ac2115f022f0')
        charging = charging_engine.ChargingEngine(purchase, payment_method='credit_card', credit_card=credit_card)

        charging._generate_cdr = fake_cdr_generation
        charging._check_expenditure_limits = MagicMock()
        charging._update_actor_balance = MagicMock()
        charging.resolve_charging(new_purchase=True)

        purchase = Purchase.objects.get(pk='61005aba8e05ac2115f022f0')
        bills = purchase.bill

        self.assertEqual(len(bills), 1)

        contract = purchase.contract
        charges = contract.charges

        self.assertEqual(len(charges), 1)
        self.assertEqual(charges[0]['cost'], 5)
        self.assertEqual(charges[0]['currency'], 'EUR')
        self.assertEqual(charges[0]['concept'], 'initial charge')

        price_model = contract.pricing_model

        self.assertTrue('single_payment' in price_model)
        self.assertFalse('subscription' in price_model)
        self.assertFalse('pay_per_use' in price_model)

        self.assertEqual(len(price_model['single_payment']), 1)
        self.assertEqual(price_model['single_payment'][0]['title'], 'Price component 1')
        self.assertEqual(price_model['single_payment'][0]['value'], '5.0')

    def test_charging_single_payment_parts(self):

        # Load model
        model = os.path.join(settings.BASEDIR, 'wstore')
        model = os.path.join(model, 'charging_engine')
        model = os.path.join(model, 'test')
        model = os.path.join(model, 'complex_sin_price.ttl')
        f = open(model, 'rb')
        graph = rdflib.Graph()
        graph.parse(data=f.read(), format='n3')
        f.close()

        user = User.objects.get(pk='51070aba8e05cc2115f022f9')
        profile = UserProfile.objects.get(user=user)

        tax_address = {
            "street": "test street",
            "postal": "20000",
            "city": "test city",
            "country": "test country"
        }

        profile.tax_address = tax_address
        org = Organization.objects.get(pk='91000aba8e06ac2115f022f0')
        profile.organization = org
        profile.save()

        purchase = Purchase.objects.get(pk='61005aba8e05ac2115f022f0')

        offering = purchase.offering
        json_model = graph.serialize(format='json-ld', auto_compact=True)

        offering.offering_description = json.loads(json_model)
        offering.save()

        credit_card = {
            'type': 'Visa',
            'number': '1234123412341234',
            'expire_year': '2018',
            'expire_month': '2',
            'cvv2': '111',
        }

        purchase = Purchase.objects.get(pk='61005aba8e05ac2115f022f0')
        charging = charging_engine.ChargingEngine(purchase, payment_method='credit_card', credit_card=credit_card)

        charging._generate_cdr = fake_cdr_generation
        charging._check_expenditure_limits = MagicMock()
        charging._update_actor_balance = MagicMock()
        charging.resolve_charging(new_purchase=True)

        purchase = Purchase.objects.get(pk='61005aba8e05ac2115f022f0')
        bills = purchase.bill
        self.assertEqual(len(bills), 1)

        contract = purchase.contract
        charges = contract.charges

        self.assertEqual(len(charges), 1)
        self.assertEqual(charges[0]['cost'], 17)
        self.assertEqual(charges[0]['currency'], 'EUR')
        self.assertEqual(charges[0]['concept'], 'initial charge')

        price_model = contract.pricing_model

        self.assertTrue('single_payment' in price_model)
        self.assertFalse('subscription' in price_model)
        self.assertFalse('pay_per_use' in price_model)

        self.assertEqual(len(price_model['single_payment']), 3)

        for pay in price_model['single_payment']:

            if pay['title'] == 'Price component 1':
                self.assertEqual(pay['title'], 'Price component 1')
                self.assertEqual(pay['value'], '5.0')

            elif pay['title'] == 'Price component 2':
                self.assertEqual(pay['title'], 'Price component 2')
                self.assertEqual(pay['value'], '5.0')

            elif pay['title'] == 'Price component 3':
                self.assertEqual(pay['title'], 'Price component 3')
                self.assertEqual(pay['value'], '7.0')


class SubscriptionChargingTestCase(TestCase):

    tags = ('fiware-ut-13',)
    fixtures = ['subscription.json']

    _to_delete = []

    @classmethod
    def setUpClass(cls):
        settings.PAYMENT_CLIENT = 'wstore.charging_engine.tests.FakeClient'
        charging_engine.subprocess = FakeSubprocess()
        super(SubscriptionChargingTestCase, cls).setUpClass()

    def test_basic_subscription_charging(self):

        # Load model
        model = os.path.join(settings.BASEDIR, 'wstore')
        model = os.path.join(model, 'charging_engine')
        model = os.path.join(model, 'test')
        model = os.path.join(model, 'basic_subs.ttl')
        f = open(model, 'rb')
        graph = rdflib.Graph()
        graph.parse(data=f.read(), format='n3')
        f.close()

        user = User.objects.get(pk='51070aba8e05cc2115f022f9')
        profile = UserProfile.objects.get(user=user)

        tax_address = {
            "street": "test street",
            "postal": "20000",
            "city": "test city",
            "country": "test country"
        }

        profile.tax_address = tax_address
        org = Organization.objects.get(pk='91000aba8e06ac2115f022f0')
        profile.organization = org
        profile.save()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')

        offering = purchase.offering
        json_model = graph.serialize(format='json-ld', auto_compact=True)

        offering.offering_description = json.loads(json_model)
        offering.save()
        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')

        credit_card = {
            'type': 'Visa',
            'number': '1234123412341234',
            'expire_year': '2018',
            'expire_month': '2',
            'cvv2': '111',
        }

        charging = charging_engine.ChargingEngine(purchase, payment_method='credit_card', credit_card=credit_card)
        charging._calculate_renovation_date = fake_renovation_date

        charging._generate_cdr = fake_cdr_generation
        charging._check_expenditure_limits = MagicMock()
        charging._update_actor_balance = MagicMock()
        charging.resolve_charging(new_purchase=True)
        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')
        contract = purchase.contract

        self.assertEqual(len(contract.charges), 1)
        self.assertEqual(contract.charges[0]['cost'], 10)
        self.assertEqual(contract.charges[0]['currency'], 'EUR')
        self.assertEqual(contract.charges[0]['concept'], 'initial charge')

        pricing_model = contract.pricing_model

        self.assertTrue('subscription' in pricing_model)
        self.assertFalse('single_payment' in pricing_model)
        self.assertFalse('pay_per_use' in pricing_model)

        for sub in pricing_model['subscription']:
            if sub['title'] == 'Price component 1':
                self.assertEqual(sub['value'], '5.0')
                self.assertEqual(sub['unit'], 'per month')
                self.assertEqual(str(sub['renovation_date']), '2013-04-01 00:00:00')
            else:
                self.assertEqual(sub['title'], 'Price component 2')
                self.assertEqual(sub['value'], '5.0')
                self.assertEqual(sub['unit'], 'per week')
                self.assertEqual(str(sub['renovation_date']), '2013-03-20 00:00:00')

    def test_basic_renovation_charging(self):

        user = User.objects.get(pk='51070aba8e05cc2115f022f9')
        profile = UserProfile.objects.get(user=user)

        tax_address = {
            "street": "test street",
            "postal": "20000",
            "city": "test city",
            "country": "test country"
        }

        profile.tax_address = tax_address
        org = Organization.objects.get(pk='91000aba8e06ac2115f022f0')
        profile.organization = org
        profile.save()

        purchase = Purchase.objects.get(pk="61005a1a8205ac3115111111")
        contract = purchase.contract

        # Change renovation date type (JSON does not allow complex types as MongoDB does)
        new_subs = []
        for sub in contract.pricing_model['subscription']:

            new_sub = sub
            new_sub['renovation_date'] = datetime.strptime(new_sub['renovation_date'], '%Y-%m-%d %H:%M:%S')
            new_subs.append(new_sub)

        contract.pricing_model['subscription'] = new_subs
        contract.save()

        credit_card = {
            'type': 'Visa',
            'number': '1234123412341234',
            'expire_year': '2018',
            'expire_month': '2',
            'cvv2': '111',
        }

        charging = charging_engine.ChargingEngine(purchase, payment_method='credit_card', credit_card=credit_card)
        charging._calculate_renovation_date = fake_renovation_date

        charging._generate_cdr = fake_cdr_generation
        charging._check_expenditure_limits = MagicMock()
        charging._update_actor_balance = MagicMock()
        charging.resolve_charging()
        purchase = Purchase.objects.get(pk="61005a1a8205ac3115111111")
        contract = purchase.contract

        self.assertEqual(len(contract.charges), 2)
        self.assertEqual(contract.charges[0]['cost'], 10)
        self.assertEqual(contract.charges[0]['currency'], 'EUR')
        self.assertEqual(contract.charges[0]['concept'], 'initial')
        self.assertEqual(contract.charges[1]['cost'], 10)
        self.assertEqual(contract.charges[1]['currency'], 'EUR')
        self.assertEqual(contract.charges[1]['concept'], 'Renovation')

        pricing_model = contract.pricing_model

        self.assertTrue('subscription' in pricing_model)
        self.assertFalse('single_payment' in pricing_model)
        self.assertFalse('pay_per_use' in pricing_model)

        for sub in pricing_model['subscription']:
            if sub['title'] == 'price component 1':
                self.assertEqual(sub['value'], '5')
                self.assertEqual(sub['unit'], 'per month')
                self.assertEqual(str(sub['renovation_date']), '2013-04-01 00:00:00')
            else:
                self.assertEqual(sub['title'], 'price component 2')
                self.assertEqual(sub['value'], '5')
                self.assertEqual(sub['unit'], 'per week')
                self.assertEqual(str(sub['renovation_date']), '2013-03-20 00:00:00')

    def test_partial_renovation(self):

        user = User.objects.get(pk='51070aba8e05cc2115f022f9')
        profile = UserProfile.objects.get(user=user)

        tax_address = {
            "street": "test street",
            "postal": "20000",
            "city": "test city",
            "country": "test country"
        }

        profile.tax_address = tax_address
        org = Organization.objects.get(pk='91000aba8e06ac2115f022f0')
        profile.organization = org
        profile.save()

        purchase = Purchase.objects.get(pk='61005aba8e06ac2015f022f0')
        contract = purchase.contract

        # Change renovation date type (JSON does not allow complex types as MongoDB does)
        new_subs = []
        for sub in contract.pricing_model['subscription']:

            new_sub = sub
            new_sub['renovation_date'] = datetime.strptime(new_sub['renovation_date'], '%Y-%m-%d %H:%M:%S')
            new_subs.append(new_sub)

        contract.pricing_model['subscription'] = new_subs
        contract.save()

        credit_card = {
            'type': 'Visa',
            'number': '1234123412341234',
            'expire_year': '2018',
            'expire_month': '2',
            'cvv2': '111',
        }

        charging = charging_engine.ChargingEngine(purchase, payment_method='credit_card', credit_card=credit_card)
        charging._calculate_renovation_date = fake_renovation_date

        charging._generate_cdr = fake_cdr_generation
        charging._check_expenditure_limits = MagicMock()
        charging._update_actor_balance = MagicMock()
        charging.resolve_charging()
        purchase = Purchase.objects.get(pk='61005aba8e06ac2015f022f0')
        contract = purchase.contract

        self.assertEqual(len(contract.charges), 2)
        self.assertEqual(contract.charges[0]['cost'], 10)
        self.assertEqual(contract.charges[0]['currency'], 'EUR')
        self.assertEqual(contract.charges[0]['concept'], 'initial')
        self.assertEqual(contract.charges[1]['cost'], 5)
        self.assertEqual(contract.charges[1]['currency'], 'EUR')
        self.assertEqual(contract.charges[1]['concept'], 'Renovation')

        pricing_model = contract.pricing_model

        self.assertTrue('subscription' in pricing_model)
        self.assertFalse('single_payment' in pricing_model)
        self.assertFalse('pay_per_use' in pricing_model)

        for s in pricing_model['subscription']:
            if s['title'] == 'price component 1':
                self.assertEqual(s['value'], '5')
                self.assertEqual(s['unit'], 'per month')
                self.assertEqual(str(s['renovation_date']), '2013-04-01 00:00:00')
            else:
                self.assertEqual(s['value'], '5')
                self.assertEqual(s['unit'], 'per week')
                self.assertEqual(str(s['renovation_date']), '2020-04-01 00:00:00')

    def test_renovation_no_subscription(self):

        user = User.objects.get(pk='51070aba8e05cc2115f022f9')
        profile = UserProfile.objects.get(user=user)

        tax_address = {
            "street": "test street",
            "postal": "20000",
            "city": "test city",
            "country": "test country"
        }

        profile.tax_address = tax_address
        org = Organization.objects.get(pk='91000aba8e06ac2115f022f0')
        profile.organization = org
        profile.save()

        purchase = Purchase.objects.get(pk="61015a1a1e06ac2015f122f0")
        charging = charging_engine.ChargingEngine(purchase)

        error = False
        try:
            charging.resolve_charging()
        except Exception, e:
            error = True
            msg = e.message

        self.assertTrue(error)
        self.assertEqual(msg, 'No subscriptions to renovate')


class PayPerUseChargingTestCase(TestCase):

    fixtures = ['payperuse.json']

    _to_delete = []

    @classmethod
    def setUpClass(cls):
        cls._auth = settings.OILAUTH
        settings.PAYMENT_CLIENT = 'wstore.charging_engine.tests.FakeClient'
        charging_engine.subprocess = FakeSubprocess()
        settings.OILAUTH = False
        super(PayPerUseChargingTestCase, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        settings.OILAUTH = cls._auth
        super(PayPerUseChargingTestCase, cls).tearDownClass()

    def test_basic_sdr_feeding(self):

        sdr = {
            'offering': {
                'name': 'test_offering',
                'organization': 'test_organization',
                'version': '1.0'
            },
            'component_label': 'invocations',
            'customer': 'test_user',
            'correlation_number': '1',
            'time_stamp': str(datetime.now()),
            'record_type': 'event',
            'value': '10',
            'unit': 'invocation'
        }

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')
        charging = charging_engine.ChargingEngine(purchase)
        charging.include_sdr(sdr)

        # Refresh the purchase
        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')
        contract = purchase.contract

        self.assertEqual(len(contract.pending_sdrs), 1)

        loaded_sdr = contract.pending_sdrs[0]

        self.assertEqual(loaded_sdr['customer'], 'test_user')
        self.assertEqual(loaded_sdr['correlation_number'], '1')
        self.assertEqual(loaded_sdr['record_type'], 'event')
        self.assertEqual(loaded_sdr['value'], '10')
        self.assertEqual(loaded_sdr['unit'], 'invocation')

    test_basic_sdr_feeding.tags = ('fiware-ut-14',)

    def test_sdr_feeding_some_applied(self):

        settings.OILAUTH = False

        sdr = {
            'offering': {
                'name': 'test_offering',
                'organization': 'test_organization',
                'version': '1.0'
            },
            'component_label': 'invocations',
            'customer': 'test_user',
            'correlation_number': '2',
            'time_stamp': str(datetime.now()),
            'record_type': 'event',
            'value': '10',
            'unit': 'invocation'
        }

        purchase = Purchase.objects.get(pk='61074ab65e05acc415f322f2')
        applied_date = purchase.contract.applied_sdrs[0]['time_stamp']
        applied_date = datetime.strptime(applied_date, '%Y-%m-%d %H:%M:%S')
        purchase.contract.applied_sdrs[0]['time_stamp'] = applied_date
        purchase.contract.save()

        charging = charging_engine.ChargingEngine(purchase)
        charging.include_sdr(sdr)

        # Refresh the purchase
        purchase = Purchase.objects.get(pk='61074ab65e05acc415f322f2')
        contract = purchase.contract

        self.assertEqual(len(contract.pending_sdrs), 1)
        self.assertEqual(len(contract.applied_sdrs), 1)
        self.assertEqual(len(contract.charges), 1)

        loaded_sdr = contract.pending_sdrs[0]

        self.assertEqual(loaded_sdr['customer'], 'test_user')
        self.assertEqual(loaded_sdr['correlation_number'], '2')
        self.assertEqual(loaded_sdr['record_type'], 'event')
        self.assertEqual(loaded_sdr['value'], '10')
        self.assertEqual(loaded_sdr['unit'], 'invocation')

    test_sdr_feeding_some_applied.tags = ('fiware-ut-14',)
    
    def test_sdr_feeding_some_pending(self):

        sdr = {
            'offering': {
                'name': 'test_offering',
                'organization': 'test_organization',
                'version': '1.0'
            },
            'component_label': 'invocations',
            'customer': 'test_user',
            'correlation_number': '2',
            'time_stamp': str(datetime.now()),
            'record_type': 'event',
            'value': '10',
            'unit': 'invocation'
        }

        purchase = Purchase.objects.get(pk='61077ab75e07a7c415f372f2')
        applied_date = purchase.contract.pending_sdrs[0]['time_stamp']
        applied_date = datetime.strptime(applied_date, '%Y-%m-%d %H:%M:%S')
        purchase.contract.pending_sdrs[0]['time_stamp'] = applied_date
        purchase.contract.save()

        charging = charging_engine.ChargingEngine(purchase)
        charging.include_sdr(sdr)

        # Refresh the purchase
        purchase = Purchase.objects.get(pk='61077ab75e07a7c415f372f2')
        contract = purchase.contract

        self.assertEqual(len(contract.pending_sdrs), 2)

        loaded_sdr = contract.pending_sdrs[1]

        self.assertEqual(loaded_sdr['customer'], 'test_user')
        self.assertEqual(loaded_sdr['correlation_number'], '2')
        self.assertEqual(loaded_sdr['record_type'], 'event')
        self.assertEqual(loaded_sdr['value'], '10')
        self.assertEqual(loaded_sdr['unit'], 'invocation')

    test_sdr_feeding_some_pending.tags = ('fiware-ut-14',)

    def test_sdr_feeding_org_owned(self):

        sdr = {
            'offering': {
                'name': 'test_offering',
                'organization': 'test_organization',
                'version': '1.0'
            },
            'component_label': 'invocations',
            'customer': 'test_user2',
            'correlation_number': '1',
            'time_stamp': str(datetime.now()),
            'record_type': 'event',
            'value': '10',
            'unit': 'invocation'
        }

        user = User.objects.get(username='test_user2')
        profile = UserProfile.objects.get(user=user)
        org = Organization.objects.get(name='test_organization1')
        profile.current_organization = org
        profile.organizations = [{
            'organization': org.pk,
            'roles': ['customer', 'provider']
        }]
        profile.save()

        purchase = Purchase.objects.get(pk='61004a9a5e95ac9115902290')
        charging = charging_engine.ChargingEngine(purchase)
        charging.include_sdr(sdr)

        # Refresh the purchase
        purchase = Purchase.objects.get(pk='61004a9a5e95ac9115902290')
        contract = purchase.contract

        self.assertEqual(len(contract.pending_sdrs), 1)

        loaded_sdr = contract.pending_sdrs[0]

        self.assertEqual(loaded_sdr['customer'], 'test_user2')
        self.assertEqual(loaded_sdr['correlation_number'], '1')
        self.assertEqual(loaded_sdr['record_type'], 'event')
        self.assertEqual(loaded_sdr['value'], '10')
        self.assertEqual(loaded_sdr['unit'], 'invocation')

    test_sdr_feeding_org_owned.tags = ('fiware-ut-14',)

    def test_sdr_feeding_invalid_user(self):

        sdr = {
            'offering': {
                'name': 'test_offering',
                'organization': 'test_organization',
                'version': '1.0'
            },
            'customer': 'test_user2',
            'correlation_number': '1',
            'time_stamp': str(datetime.now()),
            'record_type': 'event',
            'value': '10',
            'unit': 'invocation'
        }

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')
        charging = charging_engine.ChargingEngine(purchase)

        error = False
        msg = None
        try:
            charging.include_sdr(sdr)
        except Exception, e:
            error = True
            msg = e.message

        self.assertTrue(error)
        self.assertEquals(msg, 'The user has not purchased the offering')

    test_sdr_feeding_invalid_user.tags = ('fiware-ut-14',)

    def test_sdr_feeding_invalid_correlation(self):

        sdr = {
            'offering': {
                'name': 'test_offering',
                'organization': 'test_organization',
                'version': '1.0'
            },
            'customer': 'test_user',
            'correlation_number': '3',
            'time_stamp': str(datetime.now()),
            'record_type': 'event',
            'value': '10',
            'unit': 'invocation'
        }

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')
        charging = charging_engine.ChargingEngine(purchase)

        error = False
        msg = None
        try:
            charging.include_sdr(sdr)
        except Exception, e:
            error = True
            msg = e.message

        self.assertTrue(error)
        self.assertEquals(msg, 'Invalid correlation number, expected: 1')

    test_sdr_feeding_invalid_correlation.tags = ('fiware-ut-14',)

    def test_sdr_feeding_invalid_timestamp(self):

        settings.OILAUTH = False
        sdr = {
            'offering': {
                'name': 'test_offering',
                'organization': 'test_organization',
                'version': '1.0'
            },
            'customer': 'test_user',
            'correlation_number': '2',
            'time_stamp': '1980-05-01 11:10:01.234',
            'record_type': 'event',
            'value': '10',
            'unit': 'invocation'
        }

        purchase = Purchase.objects.get(pk='61074ab65e05acc415f322f2')
        applied_date = purchase.contract.applied_sdrs[0]['time_stamp']
        applied_date = datetime.strptime(applied_date, '%Y-%m-%d %H:%M:%S')
        purchase.contract.applied_sdrs[0]['time_stamp'] = applied_date
        purchase.contract.save()

        charging = charging_engine.ChargingEngine(purchase)

        error = False
        msg = None
        try:
            charging.include_sdr(sdr)
        except Exception, e:
            error = True
            msg = e.message

        self.assertTrue(error)
        self.assertEquals(msg, 'Invalid time stamp')

    test_sdr_feeding_invalid_timestamp.tags = ('fiware-ut-14',)

    def test_sdr_feeding_invalid_offering(self):

        sdr = {
            'offering': {
                'name': 'test_offering2',
                'organization': 'test_organization',
                'version': '1.0'
            },
            'customer': 'test_user',
            'correlation_number': '3',
            'time_stamp': str(datetime.now()),
            'record_type': 'event',
            'value': '10',
            'unit': 'invocation'
        }

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')
        charging = charging_engine.ChargingEngine(purchase)

        error = False
        msg = None
        try:
            charging.include_sdr(sdr)
        except Exception, e:
            error = True
            msg = e.message

        self.assertTrue(error)
        self.assertEquals(msg, 'The offering defined in the SDR is not the purchase offering')

    test_sdr_feeding_invalid_offering.tags = ('fiware-ut-14',)

    def test_sdr_feeding_invalid_purchase(self):

        sdr = {
            'offering': {
                'name': 'test_offering2',
                'organization': 'test_organization',
                'version': '1.0'
            },
            'customer': 'test_user',
            'correlation_number': '1',
            'time_stamp': str(datetime.now()),
            'record_type': 'event',
            'value': '10',
            'unit': 'invocation'
        }

        purchase = Purchase.objects.get(pk='01003ab55e043cc335f132f3')
        charging = charging_engine.ChargingEngine(purchase)

        error = False
        msg = None
        try:
            charging.include_sdr(sdr)
        except Exception, e:
            error = True
            msg = e.message

        self.assertTrue(error)
        self.assertEquals(msg, 'No pay per use parts in the pricing model of the offering')

    test_sdr_feeding_invalid_purchase.tags = ('fiware-ut-14',)

    def test_new_purchase_use(self):

        # Load model
        model = os.path.join(settings.BASEDIR, 'wstore')
        model = os.path.join(model, 'charging_engine')
        model = os.path.join(model, 'test')
        model = os.path.join(model, 'basic_use.ttl')
        f = open(model, 'rb')
        graph = rdflib.Graph()
        graph.parse(data=f.read(), format='n3')
        f.close()

        user = User.objects.get(pk='51070aba8e05cc2115f022f9')
        profile = UserProfile.objects.get(user=user)

        tax_address = {
            "street": "test street",
            "postal": "20000",
            "city": "test city",
            "country": "test country"
        }

        profile.tax_address = tax_address
        org = Organization.objects.get(pk='91000aba8e06ac2115f022f0')
        profile.organization = org
        profile.save()

        purchase = Purchase.objects.get(pk='61074ab65e05acc415f77777')

        offering = purchase.offering
        json_model = graph.serialize(format='json-ld', auto_compact=True)

        offering.offering_description = json.loads(json_model)
        offering.save()

        charging = charging_engine.ChargingEngine(purchase)

        charging._generate_cdr = fake_cdr_generation
        charging._check_expenditure_limits = MagicMock()
        charging._update_actor_balance = MagicMock()
        charging.resolve_charging(new_purchase=True)

        purchase = Purchase.objects.get(pk='61074ab65e05acc415f77777')

        bills = purchase.bill
        self.assertEqual(len(bills), 1)

        self.assertEqual(purchase.state, 'paid')
        contract = purchase.contract

        self.assertEqual(len(contract.charges), 0)
        price_model = contract.pricing_model

        self.assertFalse('single_payment' in price_model)
        self.assertFalse('subscription' in price_model)
        self.assertTrue('pay_per_use' in price_model)

        self.assertEqual(len(price_model['pay_per_use']), 1)
        self.assertEqual(price_model['pay_per_use'][0]['title'], 'Pay per use')
        self.assertEqual(price_model['pay_per_use'][0]['value'], '5.0')
        self.assertEqual(price_model['pay_per_use'][0]['unit'], 'invocation')
        self.assertEqual(price_model['pay_per_use'][0]['currency'], 'EUR')

    test_new_purchase_use.tags = ('fiware-ut-16',)

    def test_basic_resolve_use_charging(self):

        user = User.objects.get(pk='51070aba8e05cc2115f022f9')
        profile = UserProfile.objects.get(user=user)

        tax_address = {
            "street": "test street",
            "postal": "20000",
            "city": "test city",
            "country": "test country"
        }

        profile.tax_address = tax_address
        org = Organization.objects.get(pk='91000aba8e06ac2115f022f0')
        profile.organization = org
        profile.save()

        purchase = Purchase.objects.get(pk='61077ab75e07a7c415f372f2')
        credit_card = {
            'type': 'Visa',
            'number': '1234123412341234',
            'expire_year': '2018',
            'expire_month': '2',
            'cvv2': '111',
        }

        charging = charging_engine.ChargingEngine(purchase, payment_method='credit_card', credit_card=credit_card)

        charging._generate_cdr = fake_cdr_generation
        charging._check_expenditure_limits = MagicMock()
        charging._update_actor_balance = MagicMock()
        charging.resolve_charging(sdr=True)

        purchase = Purchase.objects.get(pk='61077ab75e07a7c415f372f2')

        bills = purchase.bill
        self.assertEqual(len(bills), 1)

        self.assertEqual(purchase.state, 'paid')

        contract = purchase.contract

        self.assertEqual(len(contract.charges), 1)
        self.assertEqual(contract.charges[0]['cost'], 10.00)
        self.assertEqual(contract.charges[0]['concept'], 'pay per use')

        self.assertEqual(len(contract.pending_sdrs), 0)
        self.assertEqual(len(contract.applied_sdrs), 1)

    test_basic_resolve_use_charging.tags = ('fiware-ut-15',)

    def test_resolve_use_charging_no_sdr(self):

        purchase = Purchase.objects.get(pk='61004a9a5e95ac9115902290')
        charging = charging_engine.ChargingEngine(purchase)

        error = False
        msg = None
        try:
            charging.resolve_charging(sdr=True)
        except Exception, e:
            error = True
            msg = e.message

        self.assertTrue(error)
        self.assertEquals(msg, 'No SDRs to charge')

    test_resolve_use_charging_no_sdr.tags = ('fiware-ut-15',)


class AsynchronousPaymentTestCase(TestCase):

    tags = ('fiware-ut-17',)
    fixtures = ['async.json']

    _to_delete = []

    @classmethod
    def setUpClass(cls):
        settings.PAYMENT_CLIENT = 'wstore.charging_engine.tests.FakeClient'
        charging_engine.subprocess = FakeSubprocess()
        charging_engine.threading = FakeThreading()
        super(AsynchronousPaymentTestCase, cls).setUpClass()

    def test_basic_asynchronous_payment(self):

        # Load model
        model = os.path.join(settings.BASEDIR, 'wstore')
        model = os.path.join(model, 'charging_engine')
        model = os.path.join(model, 'test')
        model = os.path.join(model, 'basic_price.ttl')
        f = open(model, 'rb')
        graph = rdflib.Graph()
        graph.parse(data=f.read(), format='n3')
        f.close()

        user = User.objects.get(pk='51070aba8e05cc2115f022f9')
        profile = UserProfile.objects.get(user=user)

        tax_address = {
            "street": "test street",
            "postal": "20000",
            "city": "test city",
            "country": "test country"
        }

        profile.tax_address = tax_address
        org = Organization.objects.get(pk='91000aba8e06ac2115f022f0')
        profile.organization = org
        profile.save()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')

        offering = purchase.offering
        json_model = graph.serialize(format='json-ld', auto_compact=True)

        offering.offering_description = json.loads(json_model)
        offering.save()

        # First step
        charging = charging_engine.ChargingEngine(purchase, payment_method='paypal')
        url = charging.resolve_charging(new_purchase=True)

        self.assertEqual(url, 'https://www.sandbox.paypal.com/webscr?cmd=_express-checkout&token=11111111')
        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')

        self.assertEqual(purchase.state, 'pending')
        self.assertEqual(len(purchase.bill), 0)

        contract = purchase.contract
        self.assertEqual(len(contract.charges), 0)
        self.assertEqual(contract.pending_payment['price'], '5.00')
        self.assertEqual(contract.pending_payment['concept'], 'initial charge')

        model = contract.pending_payment['related_model']
        self.assertEqual(len(model['single_payment']), 1)
        self.assertEqual(model['single_payment'][0]['title'], 'Price component 1')
        self.assertEqual(model['single_payment'][0]['value'], '5.0')

        # Second step
        charging = charging_engine.ChargingEngine(purchase)

        charging._generate_cdr = fake_cdr_generation
        charging._check_expenditure_limits = MagicMock()
        charging._update_actor_balance = MagicMock()
        charging.end_charging(contract.pending_payment['price'], contract.pending_payment['concept'], contract.pending_payment['related_model'])

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')
        self.assertEqual(purchase.state, 'paid')
        bills = purchase.bill

        self.assertEqual(len(bills), 1)

        contract = purchase.contract
        self.assertEqual(len(contract.charges), 1)

        self.assertEqual(contract.charges[0]['cost'], '5.00')
        self.assertEqual(contract.charges[0]['currency'], 'EUR')
        self.assertEqual(contract.charges[0]['concept'], 'initial charge')

        self.assertEqual(contract.pending_payment, {})

    def test_timeout(self):

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')
        charging = charging_engine.ChargingEngine(purchase)

        def fakeroll(purch):
            purch.state = 'rollback'
            purch.save()

        charging_engine.rollback = fakeroll
        charging._timeout_handler()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')
        self.assertEqual(purchase.state, 'rollback')

    def test_timeout_locked(self):
        purchase = Purchase.objects.get(pk='61004aba5e05acc115f02111')
        charging = charging_engine.ChargingEngine(purchase)

        connection = MongoClient()
        db = connection[settings.DATABASES['default']['NAME']]

        raw_purchase = db.wstore_purchase.find_one({'_id': ObjectId(purchase.pk)})
        raw_purchase['_lock'] = True

        db.wstore_purchase.save(raw_purchase)

        def fakeroll(purch):
            purch.state = 'rollback'
            purch.save()

        charging_engine.rollback = fakeroll
        charging._timeout_handler()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f02111')
        self.assertEqual(purchase.state, 'pending')

    def test_timeout_finished(self):
        purchase = Purchase.objects.get(pk='61004aba5e05acc115f02222')
        charging = charging_engine.ChargingEngine(purchase)

        connection = MongoClient()
        db = connection[settings.DATABASES['default']['NAME']]

        raw_purchase = db.wstore_purchase.find_one({'_id': ObjectId(purchase.pk)})
        raw_purchase['_lock'] = False

        db.wstore_purchase.save(raw_purchase)

        def fakeroll(purch):
            purch.state = 'rollback'
            purch.save()

        charging_engine.rollback = fakeroll
        charging._timeout_handler()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f02222')
        self.assertEqual(purchase.state, 'paid')


class ChargingDaemonTestCase(TestCase):

    tags = ('fiware-ut-15',)
    fixtures = ['use_daemon.json']
    _command = None

    @classmethod
    def setUpClass(cls):

        resolve_use_charging.ChargingEngine = FakeChargingEngine
        cls._command = resolve_use_charging.Command()
        super(ChargingDaemonTestCase, cls).setUpClass()

    def test_basic_charging_daemon(self):

        # Fill userprofile model
        user = User.objects.get(pk='51000aba8e05ac2115f022f9')
        org = Organization.objects.get(pk='91000aba8e06ac2115f022f0')

        user.userprofile.organization = org
        user.userprofile.payment_info = {
        }

        user.userprofile.save()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')

        # Add dateinfo to sdr
        pending_sdrs = []
        pending_sdrs.append({
            'time_stamp': datetime(2013, 04, 01, 00, 00, 00, 00)
        })

        purchase.contract.pending_sdrs = pending_sdrs

        purchase.contract.save()

        # Run the method
        self._command.handle()

        # Check the contract
        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')

        contract = purchase.contract

        self.assertEqual(len(contract.pending_sdrs), 0)
        self.assertEqual(len(contract.applied_sdrs), 1)

    def test_charging_daemon_multiple_sdrs(self):

        # Fill userprofile model
        user = User.objects.get(pk='51000aba8e05ac2115f022f9')
        org = Organization.objects.get(pk='91000aba8e06ac2115f022f0')

        user.userprofile.organization = org
        user.userprofile.payment_info = {
        }

        user.userprofile.save()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')

        # Add dateinfo to sdr
        pending_sdrs = []
        pending_sdrs.append({
            'time_stamp': datetime(2013, 04, 01, 00, 00, 00, 00)
        })
        pending_sdrs.append({
            'time_stamp': datetime(2013, 04, 02, 00, 00, 00, 00)
        })
        pending_sdrs.append({
            'time_stamp': datetime(2013, 04, 03, 00, 00, 00, 00)
        })

        purchase.contract.pending_sdrs = pending_sdrs

        purchase.contract.save()

        # Run the method
        self._command.handle()

        # Check the contract
        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')

        contract = purchase.contract

        self.assertEqual(len(contract.pending_sdrs), 0)
        self.assertEqual(len(contract.applied_sdrs), 3)

    def test_charging_daemon_multiple_contracts(self):

        # Fill userprofile model
        user = User.objects.get(pk='51000aba8e05ac2115f022f9')
        org = Organization.objects.get(pk='91000aba8e06ac2115f022f0')

        user.userprofile.organization = org
        user.userprofile.payment_info = {
        }

        user.userprofile.save()

        purchase_1 = Purchase.objects.get(pk='61004aba5e05acc115f022f0')
        purchase_2 = Purchase.objects.get(pk='61004aba5e05acc115f03333')

        # Add dateinfo to sdr
        pending_sdrs_1 = []
        pending_sdrs_1.append({
            'time_stamp': datetime(2013, 04, 01, 00, 00, 00, 00)
        })

        pending_sdrs_2 = []
        pending_sdrs_2.append({
            'time_stamp': datetime(2013, 04, 01, 00, 00, 00, 00)
        })
        pending_sdrs_2.append({
            'time_stamp': datetime(2013, 04, 02, 00, 00, 00, 00)
        })
        pending_sdrs_2.append({
            'time_stamp': datetime(2013, 04, 03, 00, 00, 00, 00)
        })

        purchase_1.contract.pending_sdrs = pending_sdrs_1
        purchase_1.contract.save()

        purchase_2.contract.pending_sdrs = pending_sdrs_2
        purchase_2.contract.save()

        # Run the method
        self._command.handle()

        # Check the first contract
        purchase_1 = Purchase.objects.get(pk='61004aba5e05acc115f022f0')

        contract = purchase_1.contract

        self.assertEqual(len(contract.pending_sdrs), 0)
        self.assertEqual(len(contract.applied_sdrs), 1)

        # Check the first contract
        purchase_2 = Purchase.objects.get(pk='61004aba5e05acc115f03333')

        contract = purchase_2.contract

        self.assertEqual(len(contract.pending_sdrs), 0)
        self.assertEqual(len(contract.applied_sdrs), 3)

    def test_charging_daemon_organization_purchased(self):

        # Fill userprofile model
        user = User.objects.get(pk='51000aba8e05ac2115f022f9')
        org = Organization.objects.get(pk='91000aba8e06ac2115f022f0')

        org.payment_info = {}
        org.save()

        user.userprofile.organization = org

        user.userprofile.save()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f08888')

        # Add dateinfo to sdr
        pending_sdrs = []
        pending_sdrs.append({
            'time_stamp': datetime(2013, 04, 01, 00, 00, 00, 00)
        })

        purchase.contract.pending_sdrs = pending_sdrs

        purchase.contract.save()

        # Run the method
        self._command.handle()

        # Check the contract
        purchase = Purchase.objects.get(pk='61004aba5e05acc115f08888')

        contract = purchase.contract

        self.assertEqual(len(contract.pending_sdrs), 0)
        self.assertEqual(len(contract.applied_sdrs), 1)

    def test_charging_daemon_now_time(self):

        # Fill userprofile model
        user = User.objects.get(pk='51000aba8e05ac2115f022f9')
        org = Organization.objects.get(pk='91000aba8e06ac2115f022f0')

        user.userprofile.organization = org
        user.userprofile.payment_info = {
        }

        user.userprofile.save()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')

        # Add dateinfo to sdr
        pending_sdrs = []
        pending_sdrs.append({
            'time_stamp': datetime.now()
        })

        purchase.contract.pending_sdrs = pending_sdrs

        purchase.contract.save()

        # Run the method
        self._command.handle()

        # Check the contract
        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')

        contract = purchase.contract

        self.assertEqual(len(contract.pending_sdrs), 1)
        self.assertEqual(len(contract.applied_sdrs), 0)


class AdaptorWrapperThread():

    _context = None
    _url = None
    _cdr = None

    def __init__(self, context):
        self._context = context

    def __call__(self, url, cdr):
        self._url = url
        self._cdr = cdr
        return self

    def start(self):
        self._context._cdrs = self._cdr

@override_settings(STORE_NAME='wstore')
class CDRGeranationTestCase(TestCase):

    tags = ('fiware-ut-18',)
    fixtures = ['cdr_generation.json']
    _cdrs = None

    @classmethod
    def setUpClass(cls):
        charging_engine.RSSAdaptorThread = AdaptorWrapperThread(cls)
        charging_engine.get_country_code = lambda x: '1'
        charging_engine.get_curency_code = lambda x: '1'
        super(CDRGeranationTestCase, cls).setUpClass()

    def tearDown(self):
        self._cdrs = None
        TestCase.tearDown(self)

    def test_basic_cdr_generation(self):

        applied_parts = {
            'single_payment': [{
               'title': 'example part',
               'unit': 'single_payment',
               'currency': 'EUR',
               'value': '1'
            }]
        }

        # Load usdl
        model = os.path.join(settings.BASEDIR, 'wstore')
        model = os.path.join(model, 'charging_engine')
        model = os.path.join(model, 'test')
        model = os.path.join(model, 'basic_price.ttl')
        f = open(model, 'rb')
        graph = rdflib.Graph()
        graph.parse(data=f.read(), format='n3')
        f.close()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')
        purchase.offering.offering_description = json.loads(graph.serialize(format='json-ld', auto_compact=True))
        purchase.offering.save()

        charging = charging_engine.ChargingEngine(purchase)
        charging._generate_cdr(applied_parts, str(datetime.now()))

        self.assertEqual(len(self._cdrs), 1)

        cdr = self._cdrs[0]
        self.assertEqual(cdr['provider'], 'wstore')
        self.assertEqual(cdr['service'], 'example service')
        self.assertEqual(cdr['defined_model'], 'Single payment event')
        self.assertEqual(cdr['correlation'], '0')
        self.assertEqual(cdr['purchase'], '61004aba5e05acc115f022f0')
        self.assertEqual(cdr['offering'], 'test_offering 1.0')
        self.assertEqual(cdr['product_class'], 'use')
        self.assertEqual(cdr['description'], 'Single payment: 1 EUR')
        self.assertEqual(cdr['cost_currency'], '1')
        self.assertEqual(cdr['cost_value'], '1')
        self.assertEqual(cdr['country'], '1')
        self.assertEqual(cdr['customer'], 'test_user')

    def test_cdr_generation_initial(self):

        applied_parts = {
            'single_payment': [{
               'title': 'example part',
               'unit': 'single_payment',
               'currency': 'EUR',
               'value': '1'
            }],
            'subscription': [{
                'title': 'example part2',
                'unit': 'per month',
                'currency': 'EUR',
                'value': '10'
            }]
        }

        # Load usdl
        model = os.path.join(settings.BASEDIR, 'wstore')
        model = os.path.join(model, 'charging_engine')
        model = os.path.join(model, 'test')
        model = os.path.join(model, 'basic_price.ttl')
        f = open(model, 'rb')
        graph = rdflib.Graph()
        graph.parse(data=f.read(), format='n3')
        f.close()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')
        purchase.offering.offering_description = json.loads(graph.serialize(format='json-ld', auto_compact=True))
        purchase.offering.save()

        charging = charging_engine.ChargingEngine(purchase)
        charging._generate_cdr(applied_parts, str(datetime.now()))

        self.assertEqual(len(self._cdrs), 2)

        cdr = self._cdrs[0]
        self.assertEqual(cdr['provider'], 'wstore')
        self.assertEqual(cdr['service'], 'example service')
        self.assertEqual(cdr['defined_model'], 'Single payment event')
        self.assertEqual(cdr['correlation'], '0')
        self.assertEqual(cdr['purchase'], '61004aba5e05acc115f022f0')
        self.assertEqual(cdr['offering'], 'test_offering 1.0')
        self.assertEqual(cdr['product_class'], 'use')
        self.assertEqual(cdr['description'], 'Single payment: 1 EUR')
        self.assertEqual(cdr['cost_currency'], '1')
        self.assertEqual(cdr['cost_value'], '1')
        self.assertEqual(cdr['country'], '1')
        self.assertEqual(cdr['customer'], 'test_user')

        cdr = self._cdrs[1]
        self.assertEqual(cdr['provider'], 'wstore')
        self.assertEqual(cdr['service'], 'example service')
        self.assertEqual(cdr['defined_model'], 'Subscription event')
        self.assertEqual(cdr['correlation'], '1')
        self.assertEqual(cdr['purchase'], '61004aba5e05acc115f022f0')
        self.assertEqual(cdr['offering'], 'test_offering 1.0')
        self.assertEqual(cdr['product_class'], 'use')
        self.assertEqual(cdr['description'], 'Subscription: 10 EUR per month')
        self.assertEqual(cdr['cost_currency'], '1')
        self.assertEqual(cdr['cost_value'], '10')
        self.assertEqual(cdr['country'], '1')
        self.assertEqual(cdr['customer'], 'test_user')

    def test_cdr_generation_org_owned(self):

        applied_parts = {
            'single_payment': [{
               'title': 'example part',
               'unit': 'single_payment',
               'currency': 'EUR',
               'value': '1'
            }]
        }

        # Load usdl
        model = os.path.join(settings.BASEDIR, 'wstore')
        model = os.path.join(model, 'charging_engine')
        model = os.path.join(model, 'test')
        model = os.path.join(model, 'basic_price.ttl')
        f = open(model, 'rb')
        graph = rdflib.Graph()
        graph.parse(data=f.read(), format='n3')
        f.close()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')
        purchase.offering.offering_description = json.loads(graph.serialize(format='json-ld', auto_compact=True))
        purchase.offering.save()

        purchase.organization_owned = True
        purchase.owner_organization = Organization.objects.get(name='test_organization')
        purchase.save()

        charging = charging_engine.ChargingEngine(purchase)
        charging._generate_cdr(applied_parts, str(datetime.now()))

        self.assertEqual(len(self._cdrs), 1)

        cdr = self._cdrs[0]
        self.assertEqual(cdr['customer'], 'test_organization')

    def test_cdr_generation_use(self):

        applied_parts = {
            'charges': [{
                'accounting': [{
                'offering': {
                    'name': 'test_offering',
                    'organization': 'test_organization',
                    'version': '1.0'
                },
                'customer': 'test_user',
                'value': '15',
                'unit': 'invocation'
            },
            {
                'offering': {
                    'name': 'test_offering',
                    'organization': 'test_organization',
                    'version': '1.0'
                },
                'customer': 'test_user',
                'value': '10',
                'unit': 'invocation'
            }],
            'model': {
                'title': 'example part',
                'unit': 'invocation',
                'currency': 'EUR',
                'value': '1'
            },
            'price': 25.0
        }]}

        # Load usdl
        model = os.path.join(settings.BASEDIR, 'wstore')
        model = os.path.join(model, 'charging_engine')
        model = os.path.join(model, 'test')
        model = os.path.join(model, 'basic_price.ttl')
        f = open(model, 'rb')
        graph = rdflib.Graph()
        graph.parse(data=f.read(), format='n3')
        f.close()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')
        purchase.offering.offering_description = json.loads(graph.serialize(format='json-ld', auto_compact=True))
        purchase.offering.save()

        charging = charging_engine.ChargingEngine(purchase)
        charging._generate_cdr(applied_parts, str(datetime.now()))

        self.assertEqual(len(self._cdrs), 1)

        cdr = self._cdrs[0]
        self.assertEqual(cdr['provider'], 'wstore')
        self.assertEqual(cdr['service'], 'example service')
        self.assertEqual(cdr['defined_model'], 'Pay per use event')
        self.assertEqual(cdr['correlation'], '0')
        self.assertEqual(cdr['purchase'], '61004aba5e05acc115f022f0')
        self.assertEqual(cdr['offering'], 'test_offering 1.0')
        self.assertEqual(cdr['product_class'], 'use')
        self.assertEqual(cdr['description'], 'Fee per invocation, Consumption: 25')
        self.assertEqual(cdr['cost_currency'], '1')
        self.assertEqual(cdr['cost_value'], '25.0')
        self.assertEqual(cdr['country'], '1')
        self.assertEqual(cdr['customer'], 'test_user')


class PriceFunctionPaymentTestCase(TestCase):

    fixtures = ['price_function.json']
    tags = ('fiware-ut-27',)

    @classmethod
    def setUpClass(cls):
        cls._auth = settings.OILAUTH
        settings.PAYMENT_CLIENT = 'wstore.charging_engine.tests.FakeClient'
        charging_engine.subprocess = FakeSubprocess()
        settings.OILAUTH = False
        super(PriceFunctionPaymentTestCase, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        settings.OILAUTH = cls._auth
        super(PriceFunctionPaymentTestCase, cls).tearDownClass()
    def test_basic_price_function_payment(self):

        user = User.objects.get(pk='51070aba8e05cc2115f022f9')
        profile = user.userprofile

        tax_address = {
            "street": "test street",
            "postal": "20000",
            "city": "test city",
            "country": "test country"
        }

        profile.tax_address = tax_address
        org = Organization.objects.get(pk='91000aba8e06ac2115f022f0')
        profile.organization = org
        profile.save()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')
        credit_card = {
            'type': 'Visa',
            'number': '1234123412341234',
            'expire_year': '2018',
            'expire_month': '2',
            'cvv2': '111',
        }

        charging = charging_engine.ChargingEngine(purchase, payment_method='credit_card', credit_card=credit_card)

        charging._generate_cdr = fake_cdr_generation
        charging.resolve_charging(sdr=True)

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f022f0')

        bills = purchase.bill
        self.assertEqual(len(bills), 1)

        self.assertEqual(purchase.state, 'paid')

        contract = purchase.contract

        self.assertEqual(len(contract.charges), 1)
        self.assertEqual(contract.charges[0]['cost'], 33.00)
        self.assertEqual(contract.charges[0]['concept'], 'pay per use')

        self.assertEqual(len(contract.pending_sdrs), 0)
        self.assertEqual(len(contract.applied_sdrs), 3)

    def test_price_function_payment_renovation(self):

        user = User.objects.get(pk='51070aba8e05cc2115f022f9')
        profile = user.userprofile

        tax_address = {
            "street": "test street",
            "postal": "20000",
            "city": "test city",
            "country": "test country"
        }

        profile.tax_address = tax_address
        org = Organization.objects.get(pk='91000aba8e06ac2115f022f0')
        profile.organization = org
        profile.save()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f55555')
        contract = purchase.contract

        # Change renovation date type (JSON does not allow complex types as MongoDB does)
        new_sub = contract.pricing_model['subscription'][0]

        new_sub['renovation_date'] = datetime.strptime(new_sub['renovation_date'], '%Y-%m-%d %H:%M:%S')

        contract.pricing_model['subscription'] = [new_sub]
        contract.save()

        credit_card = {
            'type': 'Visa',
            'number': '1234123412341234',
            'expire_year': '2018',
            'expire_month': '2',
            'cvv2': '111',
        }

        charging = charging_engine.ChargingEngine(purchase, payment_method='credit_card', credit_card=credit_card)

        charging._generate_cdr = fake_cdr_generation
        charging._calculate_renovation_date = fake_renovation_date
        charging.resolve_charging()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f55555')

        bills = purchase.bill
        self.assertEqual(len(bills), 1)

        self.assertEqual(purchase.state, 'paid')

        contract = purchase.contract

        self.assertEqual(len(contract.charges), 1)
        self.assertEqual(contract.charges[0]['cost'], 38.00)
        self.assertEqual(contract.charges[0]['concept'], 'Renovation')

        self.assertEqual(len(contract.pending_sdrs), 0)
        self.assertEqual(len(contract.applied_sdrs), 3)


    def test_price_function_payment_deduction(self):

        user = User.objects.get(pk='51070aba8e05cc2115f022f9')
        profile = user.userprofile

        tax_address = {
            "street": "test street",
            "postal": "20000",
            "city": "test city",
            "country": "test country"
        }

        profile.tax_address = tax_address
        org = Organization.objects.get(pk='91000aba8e06ac2115f022f0')
        profile.organization = org
        profile.save()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f77777')
        contract = purchase.contract

        # Change renovation date type (JSON does not allow complex types as MongoDB does)
        new_sub = contract.pricing_model['subscription'][0]

        new_sub['renovation_date'] = datetime.strptime(new_sub['renovation_date'], '%Y-%m-%d %H:%M:%S')

        contract.pricing_model['subscription'] = [new_sub]
        contract.save()

        credit_card = {
            'type': 'Visa',
            'number': '1234123412341234',
            'expire_year': '2018',
            'expire_month': '2',
            'cvv2': '111',
        }

        charging = charging_engine.ChargingEngine(purchase, payment_method='credit_card', credit_card=credit_card)

        charging._generate_cdr = fake_cdr_generation
        charging._calculate_renovation_date = fake_renovation_date
        charging.resolve_charging()

        purchase = Purchase.objects.get(pk='61004aba5e05acc115f77777')

        bills = purchase.bill
        self.assertEqual(len(bills), 1)

        self.assertEqual(purchase.state, 'paid')

        contract = purchase.contract

        self.assertEqual(len(contract.charges), 1)
        self.assertEqual(contract.charges[0]['cost'], 33.30)
        self.assertEqual(contract.charges[0]['concept'], 'Renovation')

        self.assertEqual(len(contract.pending_sdrs), 0)
        self.assertEqual(len(contract.applied_sdrs), 3)

    def test_price_function_payment_exception(self):

        from wstore.charging_engine.price_resolver import PriceResolver

        resolver = PriceResolver()

        # Load testing info
        errors = {
            'Invalid argument 1': {
                'arg1': 8,
                'arg2': 'arg',
                'operation': '*'
            },
            'Invalid argument 2': {
                'arg1': 'arg',
                'arg2': 6,
                'operation': '*'
            },
            'Unsupported operation': {
                'arg1': 'arg',
                'arg2': 'arg',
                'operation': 'p'
            }
        }

        var = {
            'arg': '3'
        }
        # Check possible exceptions
        for err, info in errors.iteritems():
            error = False
            msg = None
            try:
                resolver._price_function_calculation(info, var)
            except Exception, e:
                error = True
                msg = e.message

            self.assertTrue(error)
            self.assertEquals(msg, err)
