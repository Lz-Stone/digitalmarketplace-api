from datetime import datetime, timedelta
import os

from flask import json
from app.models import Service, Supplier, ContactInformation, Framework, \
    AuditEvent, FrameworkLot, ServiceTableMixin
import mock
import pytest
from app import db, create_app
from tests.helpers import TEST_SUPPLIERS_COUNT, FixtureMixin, load_example_listing
from tests.bases import BaseApplicationTest, JSONUpdateTestMixin
from sqlalchemy.exc import IntegrityError
from dmapiclient import HTTPError
from dmutils.formats import DATETIME_FORMAT
from dmapiclient.audit import AuditTypes


class TestListServicesOrdering(BaseApplicationTest, FixtureMixin):
    def setup_services(self):
        with self.app.app_context():
            self.app.config['DM_API_SERVICES_PAGE_SIZE'] = 10

            g5_saas = load_example_listing("G5")
            g5_paas = load_example_listing("G5")
            g6_paas_2 = load_example_listing("G6-PaaS")
            g6_iaas_1 = load_example_listing("G6-IaaS")
            g6_paas_1 = load_example_listing("G6-PaaS")
            g6_saas = load_example_listing("G6-SaaS")
            g6_iaas_2 = load_example_listing("G6-IaaS")

            db.session.add(
                Supplier(supplier_id=1, name=u"Supplier 1")
            )

            def insert_service(listing, service_id, lot_id, framework_id):
                self.setup_dummy_service(
                    service_id=service_id,
                    lot_id=lot_id,
                    framework_id=framework_id,
                    **listing
                )

            # override certain fields to create ordering difference
            g6_iaas_1['serviceName'] = "b service name"
            g6_iaas_2['serviceName'] = "a service name"
            g6_paas_1['serviceName'] = "b service name"
            g6_paas_2['serviceName'] = "a service name"
            g5_paas['lot'] = "PaaS"

            insert_service(g5_paas, "123-g5-paas", 2, 3)
            insert_service(g5_saas, "123-g5-saas", 1, 3)
            insert_service(g6_iaas_1, "123-g6-iaas-1", 3, 1)
            insert_service(g6_iaas_2, "123-g6-iaas-2", 3, 1)
            insert_service(g6_paas_1, "123-g6-paas-1", 2, 1)
            insert_service(g6_paas_2, "123-g6-paas-2", 2, 1)
            insert_service(g6_saas, "123-g6-saas", 1, 1)

    def test_should_order_supplier_services_by_framework_lot_name(self):
        self.setup_services()

        response = self.client.get('/services?supplier_id=1')
        data = json.loads(response.get_data())

        assert response.status_code == 200
        assert [d['id'] for d in data['services']] == [
            '123-g6-saas',
            '123-g6-paas-2',
            '123-g6-paas-1',
            '123-g6-iaas-2',
            '123-g6-iaas-1',
            '123-g5-saas',
            '123-g5-paas',
        ]

    def test_all_services_list_ordered_by_id(self):
        self.setup_services()

        response = self.client.get('/services')
        data = json.loads(response.get_data())

        assert response.status_code == 200
        assert [d['id'] for d in data['services']] == [
            '123-g5-paas',
            '123-g5-saas',
            '123-g6-iaas-1',
            '123-g6-iaas-2',
            '123-g6-paas-1',
            '123-g6-paas-2',
            '123-g6-saas',
        ]


class TestListServices(BaseApplicationTest, FixtureMixin):
    def setup_services(self):
        with self.app.app_context():
            self.setup_dummy_suppliers(1)
            self.set_framework_status('digital-outcomes-and-specialists', 'live')
            self.setup_dummy_service(
                service_id='10000000001',
                supplier_id=0,
                framework_id=5,  # Digital Outcomes and Specialists
                lot_id=5,  # digital-outcomes
                data={"locations": [
                    "London", "Offsite", "Scotland", "Wales"
                ]
                })
            self.setup_dummy_service(
                service_id='10000000002',
                supplier_id=0,
                framework_id=5,  # Digital Outcomes and Specialists
                lot_id=6,  # digital-specialists
                data={"agileCoachLocations": ["London", "Offsite", "Scotland", "Wales"]}
            )
            self.setup_dummy_service(
                service_id='10000000003',
                supplier_id=0,
                framework_id=5,  # Digital Outcomes and Specialists
                lot_id=6,  # digital-specialists
                data={"agileCoachLocations": ["Wales"]}
            )

    def test_list_services_with_no_services(self):
        response = self.client.get('/services')
        data = json.loads(response.get_data())

        assert response.status_code == 200
        assert data['services'] == []

    def test_list_services_gets_all_statuses(self):
        self.setup_dummy_services_including_unpublished(1)
        response = self.client.get('/services')
        data = json.loads(response.get_data())

        assert response.status_code == 200
        assert len(data['services']) == 3

    def test_list_services_returns_updated_date(self):
        self.setup_dummy_services_including_unpublished(1)
        response = self.client.get('/services')
        data = json.loads(response.get_data())

        assert response.status_code == 200
        try:
            datetime.strptime(
                data['services'][0]['updatedAt'], DATETIME_FORMAT)
            assert True, "Parsed date"
        except ValueError:
            assert False, "Should be able to parse date"

    def test_list_services_gets_only_active_frameworks(self):
        with self.app.app_context():
            # the side effect of this method is to create four suppliers with ids between 0-3
            self.setup_dummy_services_including_unpublished(1)
            self.setup_dummy_service(
                service_id='2000000999',
                status='published',
                supplier_id=0,
                framework_id=2)

            response = self.client.get('/services')
            data = json.loads(response.get_data())

            assert response.status_code == 200
            assert len(data['services']) == 3

    def test_list_services_with_given_frameworks(self):
        with self.app.app_context():
            self.setup_dummy_services_including_unpublished(1)

            self.setup_dummy_service(
                service_id='2000000998',
                status='published',
                framework_id=2)
            self.setup_dummy_service(
                service_id='2000000999',
                status='published',
                framework_id=3)

            response = self.client.get('/services?framework=g-cloud-4')
            data = json.loads(response.get_data())

            assert response.status_code == 200
            assert len(data['services']) == 1

            response = self.client.get('/services?framework=g-cloud-4,g-cloud-5')
            data = json.loads(response.get_data())

            assert response.status_code == 200
            assert len(data['services']) == 2

    def test_gets_only_active_frameworks_with_status_filter(self):
        with self.app.app_context():
            # the side effect of this method is to create four suppliers with ids between 0-3
            self.setup_dummy_services_including_unpublished(1)
            self.setup_dummy_service(
                service_id='2000000999',
                status='published',
                supplier_id=0,
                framework_id=2)

            response = self.client.get('/services?status=published')
            data = json.loads(response.get_data())

            assert response.status_code == 200
            assert len(data['services']) == 1

    def test_list_services_gets_only_published(self):
        self.setup_dummy_services_including_unpublished(1)
        response = self.client.get('/services?status=published')
        data = json.loads(response.get_data())

        assert response.status_code == 200
        assert len(data['services']) == 1
        assert data['services'][0]['id'] == '2000000000'

    def test_list_services_gets_only_enabled(self):
        self.setup_dummy_services_including_unpublished(1)
        response = self.client.get('/services?status=enabled')
        data = json.loads(response.get_data())

        assert response.status_code == 200
        assert len(data['services']) == 1
        assert data['services'][0]['id'] == '2000000003'

    def test_list_services_gets_only_disabled(self):
        self.setup_dummy_services_including_unpublished(1)
        response = self.client.get('/services?status=disabled')
        data = json.loads(response.get_data())

        assert response.status_code == 200
        assert len(data['services']) == 1
        assert data['services'][0]['id'] == '2000000002'

    def test_list_services_gets_combination_of_enabled_and_disabled(self):
        self.setup_dummy_services_including_unpublished(1)
        response = self.client.get('/services?status=disabled,enabled')
        data = json.loads(response.get_data())

        assert response.status_code == 200
        assert len(data['services']) == 2
        assert data['services'][0]['id'] == '2000000002'
        assert data['services'][1]['id'] == '2000000003'

    def test_list_services_gets_combination_of_enabled_and_published(self):
        self.setup_dummy_services_including_unpublished(1)
        response = self.client.get('/services?status=published,enabled')
        data = json.loads(response.get_data())

        assert response.status_code == 200
        assert len(data['services']) == 2
        assert data['services'][0]['id'] == '2000000000'
        assert data['services'][1]['id'] == '2000000003'

    def test_list_services_returns_framework_and_lot_info(self):
        self.setup_dummy_services_including_unpublished(1)
        response = self.client.get('/services')
        data = json.loads(response.get_data())
        service = data['services'][0]

        framework_info = {
            key: value for key, value in data['services'][0].items()
            if key.startswith('framework') or key.startswith('lot')
        }
        assert framework_info == {
            'frameworkSlug': 'g-cloud-6',
            'frameworkName': 'G-Cloud 6',
            'frameworkStatus': 'live',
            'frameworkFramework': 'g-cloud',
            'lot': 'saas',
            'lotSlug': 'saas',
            'lotName': 'Software as a Service',
        }

    def test_list_services_returns_supplier_info(self):
        self.setup_dummy_services_including_unpublished(1)
        response = self.client.get('/services')
        data = json.loads(response.get_data())
        service = data['services'][0]

        assert service['supplierId'] == 0
        assert service['supplierName'] == u'Supplier 0'

    def test_paginated_list_services_page_one(self):
        self.setup_dummy_services_including_unpublished(7)

        response = self.client.get('/services')
        data = json.loads(response.get_data())

        assert response.status_code == 200
        assert len(data['services']) == 5
        assert 'page=2' in data['links']['next']
        assert 'page=2' in data['links']['last']

    def test_paginated_list_services_page_two(self):
        self.setup_dummy_services_including_unpublished(7)

        response = self.client.get('/services?page=2')
        data = json.loads(response.get_data())

        assert response.status_code == 200
        assert len(data['services']) == 4
        prev_link = data['links']['prev']
        assert 'page=1' in prev_link

    def test_paginated_list_services_page_out_of_range(self):
        self.setup_dummy_services_including_unpublished(10)

        response = self.client.get('/services?page=10')

        assert response.status_code == 404

    def test_below_one_page_number_is_404(self):
        response = self.client.get('/services?page=0')

        assert response.status_code == 404

    def test_x_forwarded_proto(self):
        prev_environ = os.environ.get('DM_HTTP_PROTO')
        os.environ['DM_HTTP_PROTO'] = 'https'
        app = create_app('test')

        with app.app_context():
            client = app.test_client()
            self.setup_authorization(app)
            response = client.get('/')
            data = json.loads(response.get_data())

        if prev_environ is None:
            del os.environ['DM_HTTP_PROTO']
        else:
            os.environ['DM_HTTP_PROTO'] = prev_environ

        assert data['links']['services.list'].startswith('https://')

    def test_invalid_page_argument(self):
        response = self.client.get('/services?page=a')

        assert response.status_code == 400
        assert b'Invalid page argument' in response.get_data()

    def test_invalid_supplier_id_argument(self):
        response = self.client.get('/services?supplier_id=a')

        assert response.status_code == 400
        assert b'Invalid supplier_id' in response.get_data()

    def test_non_existent_supplier_id_argument(self):
        response = self.client.get('/services?supplier_id=54321')

        assert response.status_code == 404

    def test_supplier_id_filter(self):
        self.setup_dummy_services_including_unpublished(15)

        response = self.client.get('/services?supplier_id=1')
        data = json.loads(response.get_data())

        assert response.status_code == 200
        assert list(filter(lambda s: s['supplierId'] == 1, data['services'])) == data['services']

    def test_supplier_id_with_no_services_filter(self):
        self.setup_dummy_services_including_unpublished(15)

        response = self.client.get(
            '/services?supplier_id=%d' % TEST_SUPPLIERS_COUNT
        )
        data = json.loads(response.get_data())

        assert response.status_code == 200
        assert list() == data['services']

    def test_supplier_should_get_all_service_on_one_page(self):
        self.setup_dummy_services_including_unpublished(21)

        response = self.client.get('/services?supplier_id=1')
        data = json.loads(response.get_data())
        assert 'next' not in data['links']
        assert len(data['services']) == 7

    def test_unknown_supplier_id(self):
        self.setup_dummy_services_including_unpublished(15)
        response = self.client.get('/services?supplier_id=100')

        assert response.status_code == 404

    def test_filter_services_by_lot_location_role(self):
        self.setup_services()
        response = self.client.get('/services?lot=digital-specialists')
        data = json.loads(response.get_data())
        assert response.status_code == 200
        assert len(data['services']) == 2

        response = self.client.get('/services?lot=digital-outcomes')
        data = json.loads(response.get_data())
        assert response.status_code == 200
        assert len(data['services']) == 1

        response = self.client.get('/services?lot=digital-specialists&location=London&role=agileCoach')
        data = json.loads(response.get_data())
        assert response.status_code == 200
        assert len(data['services']) == 1

        response = self.client.get('/services?lot=digital-specialists&location=Wales&role=agileCoach')
        data = json.loads(response.get_data())
        assert response.status_code == 200
        assert len(data['services']) == 2

        response = self.client.get('/services?lot=digital-specialists&role=agileCoach')
        data = json.loads(response.get_data())
        assert response.status_code == 200
        assert len(data['services']) == 2

    def test_cannot_filter_services_by_location_without_lot(self):
        self.setup_services()
        response = self.client.get('/services?location=Wales')
        data = json.loads(response.get_data())
        assert response.status_code == 400
        assert data['error'] == 'Lot must be specified to filter by location'

    def test_can_only_filter_by_role_for_specialists_lot(self):
        self.setup_services()
        response = self.client.get('/services?lot=digital-outcomes&role=agileCoach')
        data = json.loads(response.get_data())
        assert response.status_code == 400
        assert data['error'] == 'Role only applies to Digital Specialists lot'

    def test_role_required_for_digital_specialists_location_query(self):
        self.setup_services()
        response = self.client.get('/services?lot=digital-specialists&location=Wales')
        data = json.loads(response.get_data())
        assert response.status_code == 400
        assert data['error'] == 'Role must be specified for Digital Specialists'


class TestPostService(BaseApplicationTest, JSONUpdateTestMixin, FixtureMixin):
    endpoint = '/services/{self.service_id}'
    method = 'post'
    service_id = None

    def setup(self):
        super(TestPostService, self).setup()
        payload = load_example_listing("G6-SaaS")
        self.service_id = str(payload['id'])
        with self.app.app_context():
            db.session.add(
                Supplier(supplier_id=1, name=u"Supplier 1")
            )
            db.session.add(
                ContactInformation(
                    supplier_id=1,
                    contact_name=u"Liz",
                    email=u"liz@royal.gov.uk",
                    postcode=u"SW1A 1AA"
                )
            )
            self.setup_dummy_service(
                service_id=self.service_id,
                **payload
            )

    def _post_service_update(self, service_data, service_id=None):
        return self.client.post(
            '/services/{}'.format(service_id or self.service_id),
            data=json.dumps({
                'updated_by': 'joeblogs',
                'services': service_data
            }),
            content_type='application/json')

    def test_can_not_post_to_root_services_url(self):
        response = self.client.post(
            "/services",
            data=json.dumps(
                {'updated_by': 'joeblogs',
                 'services': {
                     'serviceName': 'new service name'}}),
            content_type='application/json')

        assert response.status_code == 405

    def test_post_returns_404_if_no_service_to_update(self):
        response = self.client.post(
            "/services/9999999999",
            data=json.dumps(
                {'updated_by': 'joeblogs',
                 'services': {
                     'serviceName': 'new service name'}}),
            content_type='application/json')

        assert response.status_code == 404

    def test_no_content_type_causes_failure(self):
        with self.app.app_context():
            response = self.client.post(
                '/services/%s' % self.service_id,
                data=json.dumps(
                    {'updated_by': 'joeblogs',
                     'services': {
                         'serviceName': 'new service name'}}))

            assert response.status_code == 400
            assert b'Unexpected Content-Type' in response.get_data()

    def test_invalid_content_type_causes_failure(self):
        with self.app.app_context():
            response = self.client.post(
                '/services/%s' % self.service_id,
                data=json.dumps(
                    {'updated_by': 'joeblogs',
                     'services': {
                         'serviceName': 'new service name'}}),
                content_type='application/octet-stream')

            assert response.status_code == 400
            assert b'Unexpected Content-Type' in response.get_data()

    def test_invalid_json_causes_failure(self):
        with self.app.app_context():
            response = self.client.post(
                '/services/%s' % self.service_id,
                data="ouiehdfiouerhfuehr",
                content_type='application/json')

            assert response.status_code == 400
            assert b'Invalid JSON' in response.get_data()

    def test_can_post_a_valid_service_update(self):
        with self.app.app_context():
            response = self._post_service_update({'serviceName': 'new service name'})
            assert response.status_code == 200

            response = self.client.get('/services/{}'.format(self.service_id))
            data = json.loads(response.get_data())
            assert data['services']['serviceName'] == 'new service name'
            assert response.status_code == 200

    def test_valid_service_update_creates_audit_event(self):
        with self.app.app_context():
            response = self._post_service_update({'serviceName': 'new service name'})
            assert response.status_code == 200

            audit_response = self.client.get('/audit-events')
            assert audit_response.status_code == 200
            data = json.loads(audit_response.get_data())

            assert len(data['auditEvents']) == 1

            update_event = data['auditEvents'][0]
            assert update_event['type'] == 'update_service'
            assert update_event['user'] == 'joeblogs'
            assert update_event['data']['serviceId'] == self.service_id

    def test_service_update_audit_event_links_to_both_archived_services(self):
        with self.app.app_context():
            for name in ['new service name', 'new new service name']:
                response = self._post_service_update({'serviceName': name})
                assert response.status_code == 200

            audit_response = self.client.get('/audit-events')
            assert audit_response.status_code == 200
            data = json.loads(audit_response.get_data())

            assert len(data['auditEvents']) == 2
            update_event = data['auditEvents'][1]

            old_version = update_event['links']['oldArchivedService']
            new_version = update_event['links']['newArchivedService']

            assert '/archived-services/' in old_version
            assert '/archived-services/' in new_version
            assert int(old_version.split('/')[-1]) + 1 == int(new_version.split('/')[-1])
            assert data['auditEvents'][0]['data']['supplierName'] == 'Supplier 1'
            assert data['auditEvents'][0]['data']['supplierId'] == 1

    def test_can_post_a_valid_service_update_on_several_fields(self):
        with self.app.app_context():
            response = self._post_service_update({
                'serviceName': 'new service name',
                'incidentEscalation': False,
                'serviceTypes': ['Software development tools']}
            )
            assert response.status_code == 200

            response = self.client.get('/services/%s' % self.service_id)
            data = json.loads(response.get_data())
            assert data['services']['serviceName'] == 'new service name'
            assert data['services']['incidentEscalation'] is False
            assert data['services']['serviceTypes'][0] == 'Software development tools'
            assert response.status_code == 200

    def test_can_post_a_valid_service_update_with_list(self):
        with self.app.app_context():
            support_types = ['Service desk', 'Email', 'Phone', 'Live chat', 'Onsite']
            response = self._post_service_update({'supportTypes': support_types})
            assert response.status_code == 200

            response = self.client.get('/services/%s' % self.service_id)
            data = json.loads(response.get_data())

            assert all(i in support_types for i in data['services']['supportTypes']) is True
            assert response.status_code == 200

    def test_can_post_a_valid_service_update_with_object(self):
        with self.app.app_context():
            identity_authentication_controls = {
                "value": ["Authentication federation"],
                "assurance": "CESG-assured components"
            }
            response = self._post_service_update({'identityAuthenticationControls': identity_authentication_controls})
            assert response.status_code == 200

            response = self.client.get('/services/%s' % self.service_id)
            data = json.loads(response.get_data())

            updated_auth_controls = \
                data['services']['identityAuthenticationControls']
            assert response.status_code == 200
            assert updated_auth_controls['assurance'] == 'CESG-assured components'
            assert len(updated_auth_controls['value']) == 1
            assert ('Authentication federation' in updated_auth_controls['value']) is True

    def test_invalid_field_not_accepted_on_update(self):
        with self.app.app_context():
            response = self._post_service_update({'thisIsInvalid': 'so I should never see this'})

            assert response.status_code == 400
            assert 'Additional properties are not allowed' in "{}".format(
                json.loads(response.get_data())['error']['_form']
            )

    def test_invalid_field_value_not_accepted_on_update(self):
        with self.app.app_context():
            response = self._post_service_update({'priceUnit': 'per Truth'})

            assert response.status_code == 400
            assert "no_unit_specified" in json.loads(response.get_data())['error']['priceUnit']

    def test_updated_service_is_archived_right_away(self):
        with self.app.app_context():
            response = self._post_service_update({'serviceName': 'new service name'})
            assert response.status_code == 200

            archived_state = self.client.get(
                '/archived-services?service-id=' + self.service_id).get_data()
            archived_service_json = json.loads(archived_state)['services'][-1]

            assert archived_service_json['serviceName'] == 'new service name'

    def test_updated_service_archive_is_listed_in_chronological_order(self):
        with self.app.app_context():
            for name in ['new service name', 'new new service name']:
                response = self._post_service_update({'serviceName': name})
                assert response.status_code == 200

            archived_state = self.client.get(
                '/archived-services?service-id=' +
                self.service_id).get_data()
            archived_service_json = json.loads(archived_state)['services']

            # initial service creation is done using `setup_dummy_service` in setup(), which skips the archiving process
            # only the two updates done at the beginning of this test will be archived
            assert [s['serviceName'] for s in archived_service_json] == ['new service name', 'new new service name']

    def test_updated_service_should_be_archived_on_each_update(self):
        with self.app.app_context():
            for i in range(5):
                response = self._post_service_update({'serviceName': 'new service name' + str(i)})
                assert response.status_code == 200

            archived_state = self.client.get(
                '/archived-services?service-id=' + self.service_id).get_data()
            assert len(json.loads(archived_state)['services']) == 5

    def test_writing_full_service_back(self):
        with self.app.app_context():
            response = self.client.get('/services/%s' % self.service_id)
            data = json.loads(response.get_data())
            response = self._post_service_update(data['services'])

            assert response.status_code == 200

    def test_should_404_if_no_archived_service_found_by_pk(self):
        response = self.client.get('/archived-services/5')
        assert response.status_code == 404

    def test_return_404_if_no_archived_service_by_service_id(self):
        response = self.client.get(
            '/archived-services?service-id=12345678901234')
        assert response.status_code == 404

    def test_should_400_if_invalid_service_id(self):
        response = self.client.get('/archived-services?service-id=not-valid')
        assert response.status_code == 400
        assert b'Invalid service ID supplied' in response.get_data()
        response = self.client.get(
            '/archived-services?service-id=1234567890.1')
        assert response.status_code == 400
        assert b'Invalid service ID supplied' in response.get_data()
        response = self.client.get('/archived-services?service-id=')
        assert response.status_code == 400
        assert b'Invalid service ID supplied' in response.get_data()
        response = self.client.get('/archived-services')
        assert response.status_code == 400
        assert b'Invalid service ID supplied' in response.get_data()

    def test_should_400_if_mismatched_service_id(self):
        response = self.client.post(
            '/services/%s' % self.service_id,
            data=json.dumps(
                {'updated_by': 'joeblogs',
                 'services': {
                     'serviceName': 'new service name', 'id': 'differentId'}}),
            content_type='application/json')

        assert response.status_code == 400
        assert b'id parameter must match id in data' in response.get_data()

    def test_should_not_update_status_through_service_post(self):
        response = self._post_service_update({'status': 'enabled'})
        assert response.status_code == 200

        response = self.client.get('/services/%s' % self.service_id)
        data = json.loads(response.get_data())

        assert data['services']['status'] == 'published'

    def test_should_update_service_with_valid_statuses(self):
        valid_statuses = ServiceTableMixin.STATUSES

        for status in valid_statuses:
            response = self.client.post(
                '/services/{0}/status/{1}'.format(
                    self.service_id,
                    status
                ),
                data=json.dumps(
                    {'updated_by': 'joeblogs'}),
                content_type='application/json'
            )

            assert response.status_code == 200
            data = json.loads(response.get_data())
            assert status == data['services']['status']

    def test_update_service_status_creates_audit_event(self):
        response = self.client.post(
            '/services/{0}/status/{1}'.format(
                self.service_id,
                "disabled"
            ),
            data=json.dumps(
                {'updated_by': 'joeblogs'}),
            content_type='application/json'
        )

        assert response.status_code == 200

        audit_response = self.client.get('/audit-events')
        assert audit_response.status_code == 200
        data = json.loads(audit_response.get_data())

        assert len(data['auditEvents']) == 1
        assert data['auditEvents'][0]['type'] == 'update_service_status'
        assert data['auditEvents'][0]['user'] == 'joeblogs'
        assert data['auditEvents'][0]['data']['serviceId'] == self.service_id
        assert data['auditEvents'][0]['data']['new_status'] == 'disabled'
        assert data['auditEvents'][0]['data']['old_status'] == 'published'

        # initial service creation is done using `setup_dummy_service` in setup(), which skips the archiving process
        # only the two updates done at the beginning of this test will be archived
        assert data['auditEvents'][0]['data']['oldArchivedServiceId'] is None
        assert 'oldArchivedService' not in data['auditEvents'][0]['links']

        assert data['auditEvents'][0]['data']['newArchivedServiceId'] is not None
        assert '/archived-services/' in data['auditEvents'][0]['links']['newArchivedService']

    def test_should_400_with_invalid_statuses(self):
        invalid_statuses = [
            "unpublished",  # not a permissible state
            "enabeld",  # typo
        ]

        for status in invalid_statuses:
            response = self.client.post(
                '/services/{0}/status/{1}'.format(
                    self.service_id,
                    status
                ),
                data=json.dumps(
                    {'updated_by': 'joeblogs'}),
                content_type='application/json'
            )

            assert response.status_code == 400
            assert 'is not a valid status' in json.loads(response.get_data())['error']
            # assert that valid status names are returned in the response
            for valid_status in ServiceTableMixin.STATUSES:
                assert valid_status in json.loads(response.get_data())['error']

    def test_should_404_without_status_parameter(self):
        response = self.client.post(
            '/services/{0}/status/'.format(
                self.service_id,
            ),
            data=json.dumps(
                {'updated_by': 'joeblogs'}),
            content_type='application/json'
        )

        assert response.status_code == 404

    def test_json_postgres_field_should_not_include_column_fields(self):
        non_json_fields = [
            'supplierName', 'links', 'frameworkSlug', 'updatedAt', 'createdAt', 'frameworkName', 'status', 'id']
        with self.app.app_context():
            response = self.client.get('/services/{}'.format(self.service_id))
            data = json.loads(response.get_data())

            response = self._post_service_update(data['services'])
            assert response.status_code == 200

            service = Service.query.filter(Service.service_id == self.service_id).first()

            for key in non_json_fields:
                assert key not in service.data


@mock.patch('app.service_utils.search_api_client')
class TestShouldCallSearchApiOnPutToCreateService(BaseApplicationTest):
    def setup(self):
        super(TestShouldCallSearchApiOnPutToCreateService, self).setup()
        with self.app.app_context():
            db.session.add(
                Supplier(supplier_id=1, name=u"Supplier 1")
            )

            db.session.commit()

    def test_should_index_on_service_put(self, search_api_client):
        with self.app.app_context():
            search_api_client.index.return_value = True

            payload = load_example_listing("G6-IaaS")
            payload['id'] = "1234567890123456"
            response = self.client.put(
                '/services/1234567890123456',
                data=json.dumps(
                    {
                        'updated_by': 'joeblogs',
                        'services': payload}
                ),
                content_type='application/json')

            search_api_client.index.assert_called_with(
                "1234567890123456",
                json.loads(response.get_data())['services']
            )

    def test_should_not_index_on_service_on_expired_frameworks(
            self, search_api_client
    ):
        with self.app.app_context():
            search_api_client.index.return_value = True

            payload = load_example_listing("G4")
            res = self.client.put(
                '/services/' + payload["id"],
                data=json.dumps(
                    {
                        'updated_by': 'joeblogs',
                        'services': payload}
                ),
                content_type='application/json')

            assert res.status_code == 201
            assert Service.query.filter(Service.service_id == payload["id"]).first() is not None
            assert search_api_client.index.called is False

    def test_should_ignore_index_error_on_service_put(self, search_api_client):
        with self.app.app_context():
            search_api_client.index.side_effect = HTTPError()

            payload = load_example_listing("G6-IaaS")
            payload['id'] = "1234567890123456"
            response = self.client.put(
                '/services/1234567890123456',
                data=json.dumps(
                    {
                        'updated_by': 'joeblogs',
                        'services': payload}
                ),
                content_type='application/json')

            assert response.status_code == 201


@mock.patch('app.service_utils.search_api_client')
class TestShouldCallSearchApiOnPost(BaseApplicationTest, FixtureMixin):

    payload = None
    payload_g4 = None

    def setup(self):
        super(TestShouldCallSearchApiOnPost, self).setup()
        self.payload = load_example_listing("G6-SaaS")
        self.payload_g4 = load_example_listing("G4")
        with self.app.app_context():
            db.session.add(
                Supplier(supplier_id=1, name=u"Supplier 1")
            )
            self.setup_dummy_service(
                service_id=self.payload['id'],
                **self.payload
            )

            self.setup_dummy_service(
                service_id=self.payload_g4['id'],
                **self.payload_g4
            )

    def test_should_index_on_service_post(self, search_api_client):
        with self.app.app_context():
            search_api_client.index.return_value = True

            self.client.post(
                '/services/{}'.format(self.payload['id']),
                data=json.dumps(
                    {
                        'updated_by': 'joeblogs',
                        'services': self.payload}
                ),
                content_type='application/json')

            search_api_client.index.assert_called_with(
                self.payload['id'],
                mock.ANY
            )

    @mock.patch('app.service_utils.db.session.commit')
    def test_should_not_index_on_service_post_if_db_exception(
            self, search_api_client, db_session_commit
    ):
        with self.app.app_context():
            search_api_client.index.return_value = True
            db_session_commit.side_effect = IntegrityError(
                'message', 'statement', 'params', 'orig')

            payload = load_example_listing("G6-SaaS")
            self.client.post(
                '/services/{}'.format(self.payload['id']),
                data=json.dumps(
                    {
                        'updated_by': 'joeblogs',
                        'services': payload}
                ),
                content_type='application/json')
            assert search_api_client.index.called is False

    def test_should_not_index_on_service_on_expired_frameworks(
            self, search_api_client
    ):
        with self.app.app_context():
            search_api_client.index.return_value = True

            payload = load_example_listing("G4")
            res = self.client.post(
                '/services/{}'.format(self.payload_g4['id']),
                data=json.dumps(
                    {
                        'updated_by': 'joeblogs',
                        'services': payload}
                ),
                content_type='application/json')

            assert res.status_code == 200
            assert not search_api_client.index.called

    def test_should_ignore_index_error(self, search_api_client):
        with self.app.app_context():
            search_api_client.index.side_effect = HTTPError()

            payload = load_example_listing("G6-SaaS")
            response = self.client.post(
                '/services/{}'.format(self.payload['id']),
                data=json.dumps(
                    {
                        'updated_by': 'joeblogs',
                        'services': payload}
                ),
                content_type='application/json')

            assert response.status_code == 200, response.get_data()


class TestShouldCallSearchApiOnPostStatusUpdate(BaseApplicationTest, FixtureMixin):
    def setup(self):
        super(TestShouldCallSearchApiOnPostStatusUpdate, self).setup()
        now = datetime.utcnow()
        self.services = {}

        valid_statuses = ServiceTableMixin.STATUSES

        with self.app.app_context():
            db.session.add(
                Supplier(supplier_id=1, name=u"Supplier 1")
            )

            for index, status in enumerate(valid_statuses):
                payload = load_example_listing("G6-SaaS")

                # give each service a different id.
                new_id = int(payload['id']) + index
                payload['id'] = "{}".format(new_id)

                self.services[status] = payload.copy()

                self.setup_dummy_service(
                    service_id=self.services[status]['id'],
                    status=status,
                    **payload
                )

            assert db.session.query(Service).count() == 3

    def _get_service_from_database_by_service_id(self, service_id):
        with self.app.app_context():
            return Service.query.filter(
                Service.service_id == service_id).first()

    def _post_update_status(self, old_status, new_status,
                            service_is_indexed, service_is_deleted,
                            expected_status_code):

        with mock.patch('app.service_utils.search_api_client') \
                as search_api_client:

            search_api_client.index.return_value = True
            search_api_client.delete.return_value = True

            response = self.client.post(
                '/services/{0}/status/{1}'.format(
                    self.services[old_status]['id'],
                    new_status
                ),
                data=json.dumps(
                    {'updated_by': 'joeblogs'}),
                content_type='application/json'
            )

            # Check response after posting an update
            assert response.status_code == expected_status_code

            # Exit function if update was not successful
            if expected_status_code != 200:
                return

            service = self._get_service_from_database_by_service_id(
                self.services[old_status]['id'])

            # Check that service in database has been updated
            assert new_status == service.status

            # Check that search_api_client is doing the right thing
            if service_is_indexed:
                search_api_client.index.assert_called_with(
                    service.service_id,
                    json.loads(response.get_data())['services']
                )
            else:
                assert not search_api_client.index.called

            if service_is_deleted:
                search_api_client.delete.assert_called_with(service.service_id)
            else:
                assert not search_api_client.delete.called

    def test_should_index_on_service_status_changed_to_published(self):

        self._post_update_status(
            old_status='enabled',
            new_status='published',
            service_is_indexed=True,
            service_is_deleted=False,
            expected_status_code=200,
        )

    def test_should_not_index_on_service_status_was_already_published(self):

        self._post_update_status(
            old_status='published',
            new_status='published',
            service_is_indexed=False,
            service_is_deleted=False,
            expected_status_code=200,
        )

    def test_should_delete_on_update_service_status_to_not_published(self):

        self._post_update_status(
            old_status='published',
            new_status='enabled',
            service_is_indexed=False,
            service_is_deleted=True,
            expected_status_code=200,
        )

    def test_should_not_delete_on_service_status_was_never_published(self):

        self._post_update_status(
            old_status='disabled',
            new_status='enabled',
            service_is_indexed=False,
            service_is_deleted=False,
            expected_status_code=200,
        )

    @mock.patch('app.search_api_client')
    def test_should_ignore_index_error(self, search_api_client):
        search_api_client.index.side_effect = HTTPError()

        response = self.client.post(
            '/services/{0}/status/{1}'.format(
                self.services['enabled']['id'],
                'published'
            ),
            data=json.dumps(
                {'updated_by': 'joeblogs'}),
            content_type='application/json'
        )

        assert response.status_code == 200

    @mock.patch('app.search_api_client')
    def test_should_ignore_index_delete_error(self, search_api_client):
        search_api_client.delete.side_effect = HTTPError()

        response = self.client.post(
            '/services/{0}/status/{1}'.format(
                self.services['published']['id'],
                'enabled'
            ),
            data=json.dumps(
                {'updated_by': 'joeblogs'}),
            content_type='application/json'
        )

        assert response.status_code == 200


class TestPutService(BaseApplicationTest, JSONUpdateTestMixin, FixtureMixin):
    method = "put"
    endpoint = "/services/{self.service_id}"
    service = service_id = None

    def setup(self):
        super(TestPutService, self).setup()
        self.service = load_example_listing("G6-SaaS")
        self.service_id = self.service['id']
        with self.app.app_context():
            # need a supplier_id of '1' because our service has it hardcoded
            self.setup_dummy_suppliers(2)
            db.session.commit()

    def test_json_postgres_data_column_should_not_include_column_fields(self):
        non_json_fields = [
            'supplierName', 'links', 'frameworkSlug', 'updatedAt', 'createdAt', 'frameworkName', 'status', 'id',
            'supplierId', 'updatedAt', 'createdAt']
        with self.app.app_context():
            response = self.client.put(
                '/services/{}'.format(self.service_id),
                data=json.dumps({
                    'updated_by': 'joeblogs',
                    'services': self.service,
                }),
                content_type='application/json')

            assert response.status_code == 201

            service = Service.query.filter(Service.service_id == self.service_id).first()
            for key in non_json_fields:
                assert key not in service.data

    @mock.patch('app.search_api_client')
    def test_add_a_new_service(self, search_api_client):
        with self.app.app_context():
            search_api_client.index.return_value = "bar"

            response = self.client.put(
                '/services/{}'.format(self.service_id),
                data=json.dumps({
                    'updated_by': 'joeblogs',
                    'services': self.service
                }),
                content_type='application/json')

            assert response.status_code == 201
            now = datetime.utcnow()

            response = self.client.get("/services/{}".format(self.service_id))
            service = json.loads(response.get_data())["services"]

            assert service["id"] == self.service_id
            assert service["supplierId"] == self.service['supplierId']
            assert (
                datetime.strptime(service["createdAt"], DATETIME_FORMAT).strftime("%Y-%m-%dT%H:%M:%SZ") ==
                self.service['createdAt'])
            assert abs(datetime.strptime(service["updatedAt"], DATETIME_FORMAT) - now) <= timedelta(seconds=2)

    @mock.patch('app.search_api_client')
    def test_whitespace_is_stripped_on_import(self, search_api_client):
        with self.app.app_context():
            search_api_client.index.return_value = "bar"
            self.service['serviceSummary'] = "    A new summary with   space    "
            self.service['serviceFeatures'] = [
                "    ",
                "    A feature   with space    ",
                "",
                "    A second feature with space   "
            ]

            response = self.client.put(
                '/services/{}'.format(self.service_id),
                data=json.dumps(
                    {
                        'updated_by': 'joeblogs',
                        'services': self.service}
                ),
                content_type='application/json')

            assert response.status_code == 201, response.get_data()

            response = self.client.get("/services/{}".format(self.service_id))
            service = json.loads(response.get_data())["services"]

            assert service["serviceSummary"] == "A new summary with   space"
            assert len(service["serviceFeatures"]) == 2
            assert service["serviceFeatures"][0] == "A feature   with space"
            assert service["serviceFeatures"][1] == "A second feature with space"

    @mock.patch('app.search_api_client')
    def test_add_a_new_service_creates_audit_event(self, search_api_client):
        with self.app.app_context():
            response = self.client.put(
                '/services/{}'.format(self.service_id),
                data=json.dumps(
                    {
                        'updated_by': 'joeblogs',
                        'services': self.service}
                ),
                content_type='application/json')

            assert response.status_code == 201

            audit_response = self.client.get('/audit-events')
            assert audit_response.status_code == 200
            data = json.loads(audit_response.get_data())

            assert len(data['auditEvents']) == 1
            assert data['auditEvents'][0]['type'] == 'import_service'
            assert data['auditEvents'][0]['user'] == 'joeblogs'
            assert data['auditEvents'][0]['data']['serviceId'] == self.service_id
            assert data['auditEvents'][0]['data']['supplierName'] == "Supplier 1"
            assert data['auditEvents'][0]['data']['supplierId'] == self.service["supplierId"]
            assert data['auditEvents'][0]['data']['oldArchivedServiceId'] is None
            assert 'old_archived_service' not in data['auditEvents'][0]['links']
            assert isinstance(data['auditEvents'][0]['data']['newArchivedServiceId'], int)
            assert 'newArchivedService' in data['auditEvents'][0]['links']

    def test_add_a_new_service_with_status_disabled(self):
        with self.app.app_context():
            payload = load_example_listing("G4")
            payload['id'] = "4-disabled"
            payload['status'] = "disabled"
            response = self.client.put(
                '/services/4-disabled',
                data=json.dumps({
                    'updated_by': 'joeblogs',
                    'services': payload
                }),
                content_type='application/json')

            for field in ['id', 'lot', 'supplierId', 'status']:
                payload.pop(field, None)
            assert response.status_code == 201, response.get_data()
            now = datetime.utcnow()
            service = Service.query.filter(Service.service_id == "4-disabled").first()
            assert service.status == 'disabled'
            for key in service.data:
                assert service.data[key] == payload[key]
            assert abs(service.created_at - service.updated_at) <= timedelta(seconds=0.5)
            assert abs(now - service.created_at) <= timedelta(seconds=2)

    def test_when_service_payload_has_mismatched_id(self):
        mismatched_id = int(self.service_id) * 2
        response = self.client.put(
            '/services/{}'.format(mismatched_id),
            data=json.dumps({
                'updated_by': 'joeblogs',
                'services': {'id': "{}".format(self.service_id), 'foo': 'bar'}}),
            content_type='application/json')

        assert response.status_code == 400
        assert b'id parameter must match id in data' in response.get_data()

    def test_invalid_service_id_too_short(self):
        response = self.client.put(
            '/services/abc123456',
            data=json.dumps({
                'updated_by': 'joeblogs',
                'services': {'id': 'abc123456', 'foo': 'bar'}
            }),
            content_type='application/json')

        assert response.status_code == 400
        assert b'Invalid service ID supplied' in response.get_data()

    @pytest.mark.parametrize("invalid_service_id", [('tooshort', 'this_one_is_way_too_long')])
    def test_invalid_service_ids(self, invalid_service_id):
        response = self.client.put(
            '/services/{}'.format(invalid_service_id),
            data=json.dumps({
                'updated_by': 'joeblogs',
                'services': {'id': '{}'.format(invalid_service_id), 'foo': 'bar'}}),
            content_type='application/json')

        assert response.status_code == 400
        assert b'Invalid service ID supplied' in response.get_data()

    def test_invalid_service_status(self):
        payload = load_example_listing("G4")
        payload['id'] = "4-invalid-status"
        payload['status'] = "foo"
        response = self.client.put(
            '/services/4-invalid-status',
            data=json.dumps({
                'updated_by': 'joeblogs',
                'services': payload}),
            content_type='application/json')

        assert response.status_code == 400
        assert "Invalid status value 'foo'" in json.loads(response.get_data())['error']

    def test_invalid_service_lot(self):
        payload = load_example_listing("G4")
        payload['id'] = "4-invalid-lot"
        payload['lot'] = "foo"
        response = self.client.put(
            '/services/4-invalid-lot',
            data=json.dumps({
                'updated_by': 'joeblogs',
                'services': payload}),
            content_type='application/json'
        )

        assert response.status_code == 400
        assert "Incorrect lot 'foo' for framework 'g-cloud-4'" in json.loads(response.get_data())['error']

    def test_invalid_service_data(self):
        self.service['priceMin'] = 23.45

        response = self.client.put(
            '/services/{}'.format(self.service_id),
            data=json.dumps({
                'updated_by': 'joeblogs',
                'services': self.service
            }),
            content_type='application/json')

        assert response.status_code == 400
        assert "23.45 is not of type" in json.loads(response.get_data())['error']['priceMin']

    def test_add_a_service_with_unknown_supplier_id(self):
        with self.app.app_context():
            self.service['supplierId'] = 100
            response = self.client.put(
                '/services/{}'.format(self.service_id),
                data=json.dumps({
                    'updated_by': 'joeblogs',
                    'services': self.service
                }),
                content_type='application/json')

            assert response.status_code == 400
            assert "Invalid supplier ID '100'" in json.loads(response.get_data())['error']

    def test_supplier_name_in_service_data_is_shadowed(self):
        with self.app.app_context():
            self.service['supplierId'] = 1
            self.service['supplierName'] = u'New Name'

            response = self.client.put(
                '/services/{}'.format(self.service_id),
                data=json.dumps({
                    'updated_by': 'joeblogs',
                    'services': self.service
                }),
                content_type='application/json')

            assert response.status_code == 201

            response = self.client.get('/services/{}'.format(self.service_id))
            data = json.loads(response.get_data())

            assert response.status_code == 200
            assert data['services']['supplierName'] == u'Supplier 1'


class TestGetService(BaseApplicationTest):
    def setup(self):
        super(TestGetService, self).setup()
        now = datetime.utcnow()
        with self.app.app_context():
            db.session.add(Framework(
                id=123,
                name="expired",
                slug="expired",
                framework="g-cloud",
                status="expired",
            ))
            db.session.commit()
            db.session.add(FrameworkLot(
                framework_id=123,
                lot_id=1
            ))
            db.session.add(
                Supplier(supplier_id=1, name=u"Supplier 1")
            )
            db.session.add(
                ContactInformation(
                    supplier_id=1,
                    contact_name=u"Liz",
                    email=u"liz@royal.gov.uk",
                    postcode=u"SW1A 1AA"
                )
            )
            db.session.add(Service(service_id="123-published-456",
                                   supplier_id=1,
                                   updated_at=now,
                                   created_at=now,
                                   status='published',
                                   data={'foo': 'bar'},
                                   lot_id=1,
                                   framework_id=1))
            db.session.add(Service(service_id="123-disabled-456",
                                   supplier_id=1,
                                   updated_at=now,
                                   created_at=now,
                                   status='disabled',
                                   data={'foo': 'bar'},
                                   lot_id=1,
                                   framework_id=1))
            db.session.add(Service(service_id="123-enabled-456",
                                   supplier_id=1,
                                   updated_at=now,
                                   created_at=now,
                                   status='enabled',
                                   data={'foo': 'bar'},
                                   lot_id=1,
                                   framework_id=1))
            db.session.add(Service(service_id="123-expired-456",
                                   supplier_id=1,
                                   updated_at=now,
                                   created_at=now,
                                   status='enabled',
                                   data={'foo': 'bar'},
                                   lot_id=1,
                                   framework_id=123))
            db.session.commit()

    def test_get_non_existent_service(self):
        response = self.client.get('/services/9999999999')
        assert response.status_code == 404

    def test_invalid_service_id(self):
        response = self.client.get('/services/abc123')
        assert response.status_code == 404

    def test_get_published_service(self):
        response = self.client.get('/services/123-published-456')
        data = json.loads(response.get_data())
        assert response.status_code == 200
        assert data['services']['id'] == "123-published-456"

    def test_get_disabled_service(self):
        response = self.client.get('/services/123-disabled-456')
        data = json.loads(response.get_data())
        assert response.status_code == 200
        assert data['services']['id'] == "123-disabled-456"

    def test_get_enabled_service(self):
        response = self.client.get('/services/123-enabled-456')
        data = json.loads(response.get_data())
        assert response.status_code == 200
        assert data['services']['id'] == "123-enabled-456"

    def test_get_service_returns_supplier_info(self):
        response = self.client.get('/services/123-published-456')
        data = json.loads(response.get_data())
        assert data['services']['supplierId'] == 1
        assert data['services']['supplierName'] == u'Supplier 1'

    def test_get_service_returns_framework_and_lot_info(self):
        response = self.client.get('/services/123-published-456')
        data = json.loads(response.get_data())

        framework_info = {
            key: value for key, value in data['services'].items()
            if key.startswith('framework') or key.startswith('lot')
        }
        assert framework_info == {
            'frameworkSlug': 'g-cloud-6',
            'frameworkName': 'G-Cloud 6',
            'frameworkFramework': 'g-cloud',
            'frameworkStatus': 'live',
            'lot': 'saas',
            'lotSlug': 'saas',
            'lotName': 'Software as a Service',
        }

    def test_get_service_returns_empty_unavailability_audit_if_published(self):
        # create an audit event for the disabled service
        with self.app.app_context():
            service = Service.query.filter(
                Service.service_id == '123-published-456'
            ).first()
            audit_event = AuditEvent(
                audit_type=AuditTypes.update_service_status,
                db_object=service,
                user='joeblogs',
                data={
                    "supplierId": 1,
                    "newArchivedServiceId": 2,
                    "new_status": "published",
                    "supplierName": "Supplier 1",
                    "serviceId": "123-published-456",
                    "old_status": "disabled",
                    "oldArchivedServiceId": 1
                }
            )
            db.session.add(audit_event)
            db.session.commit()
        response = self.client.get('/services/123-disabled-456')
        data = json.loads(response.get_data())
        assert data['serviceMadeUnavailableAuditEvent'] is None

    def test_get_service_returns_unavailability_audit_if_disabled(self):
        # create an audit event for the disabled service
        with self.app.app_context():
            service = Service.query.filter(
                Service.service_id == '123-disabled-456'
            ).first()
            audit_event = AuditEvent(
                audit_type=AuditTypes.update_service_status,
                db_object=service,
                user='joeblogs',
                data={
                    "supplierId": 1,
                    "newArchivedServiceId": 2,
                    "new_status": "disabled",
                    "supplierName": "Supplier 1",
                    "serviceId": "123-disabled-456",
                    "old_status": "published",
                    "oldArchivedServiceId": 1
                }
            )
            db.session.add(audit_event)
            db.session.commit()
        response = self.client.get('/services/123-disabled-456')
        data = json.loads(response.get_data())
        assert data['serviceMadeUnavailableAuditEvent']['type'] == 'update_service_status'
        assert data['serviceMadeUnavailableAuditEvent']['user'] == 'joeblogs'
        assert 'createdAt' in data['serviceMadeUnavailableAuditEvent']
        assert data['serviceMadeUnavailableAuditEvent']['data']['serviceId'] == '123-disabled-456'
        assert data['serviceMadeUnavailableAuditEvent']['data']['old_status'] == 'published'
        assert data['serviceMadeUnavailableAuditEvent']['data']['new_status'] == 'disabled'

    def test_get_service_returns_unavailability_audit_if_published_but_framework_is_expired(self):
        # create an audit event for the disabled service
        with self.app.app_context():
            # get expired framework
            framework = Framework.query.filter(
                Framework.id == 123
            ).first()
            # create an audit event for the framework status change
            audit_event = AuditEvent(
                audit_type=AuditTypes.framework_update,
                db_object=framework,
                user='joeblogs',
                data={
                    "update": {
                        "status": "expired",
                        "clarificationQuestionsOpen": "true"
                    }
                }
            )
            # make a published service use the expired framework
            Service.query.filter(
                Service.service_id == '123-published-456'
            ).update({
                'framework_id': 123
            })
            db.session.add(audit_event)
            db.session.commit()
        response = self.client.get('/services/123-published-456')
        data = json.loads(response.get_data())
        assert data['serviceMadeUnavailableAuditEvent']['type'] == 'framework_update'
        assert data['serviceMadeUnavailableAuditEvent']['user'] == 'joeblogs'
        assert 'createdAt' in data['serviceMadeUnavailableAuditEvent']
        assert data['serviceMadeUnavailableAuditEvent']['data']['update']['status'] == 'expired'

    def test_get_service_returns_correct_unavailability_audit_if_disabled_but_framework_is_expired(self):
        # create an audit event for the disabled service
        with self.app.app_context():
            # get expired framework
            framework = Framework.query.filter(
                Framework.id == 123
            ).first()
            # create an audit event for the framework status change
            audit_event = AuditEvent(
                audit_type=AuditTypes.framework_update,
                db_object=framework,
                user='joeblogs',
                data={
                    "update": {
                        "status": "expired",
                        "clarificationQuestionsOpen": "true"
                    }
                }
            )
            # make a disabled service use the expired framework
            Service.query.filter(
                Service.service_id == '123-disabled-456'
            ).update({
                'framework_id': 123
            })
            db.session.add(audit_event)
            db.session.commit()
        response = self.client.get('/services/123-disabled-456')
        data = json.loads(response.get_data())
        assert data['serviceMadeUnavailableAuditEvent']['type'] == 'framework_update'
        assert data['serviceMadeUnavailableAuditEvent']['user'] == 'joeblogs'
        assert 'createdAt' in data['serviceMadeUnavailableAuditEvent']
        assert data['serviceMadeUnavailableAuditEvent']['data']['update']['status'] == 'expired'
