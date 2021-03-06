from flask import jsonify, abort, request
from sqlalchemy.types import String
from sqlalchemy.exc import IntegrityError, DataError
from sqlalchemy import func, orm, case, cast
import datetime

from dmapiclient.audit import AuditTypes
from dmutils.config import convert_to_boolean
from .. import main
from ...models import (
    db, Framework, DraftService, User, Supplier, SupplierFramework, AuditEvent, Lot, FrameworkAgreement
)
from ...utils import (
    get_json_from_request, json_has_required_keys, json_only_has_required_keys,
    validate_and_return_updater_request,
)
from ...framework_utils import validate_framework_agreement_details_data


@main.route('/frameworks', methods=['GET'])
def list_frameworks():
    frameworks = Framework.query.all()

    return jsonify(
        frameworks=[f.serialize() for f in frameworks]
    )


@main.route("/frameworks", methods=["POST"])
def create_framework():
    updater_json = validate_and_return_updater_request()

    json_payload = get_json_from_request()
    json_has_required_keys(json_payload, ['frameworks'])
    json_only_has_required_keys(json_payload['frameworks'], [
        "slug", "name", "framework", "status", "clarificationQuestionsOpen", "lots"
    ])

    lots = Lot.query.filter(Lot.slug.in_(json_payload["frameworks"]["lots"])).all()
    unfound_lots = set(json_payload["frameworks"]["lots"]) - set(lot.slug for lot in lots)
    if len(unfound_lots) > 0:
        abort(400, "Invalid lot slugs: {}".format(", ".join(sorted(unfound_lots))))

    try:
        framework = Framework(
            slug=json_payload["frameworks"]["slug"],
            name=json_payload["frameworks"]["name"],
            framework=json_payload["frameworks"]["framework"],
            status=json_payload["frameworks"]["status"],
            clarification_questions_open=json_payload["frameworks"]["clarificationQuestionsOpen"],
            lots=lots
        )
        db.session.add(framework)
        db.session.add(
            AuditEvent(
                audit_type=AuditTypes.create_framework,
                db_object=framework,
                user=updater_json['updated_by'],
                data={'update': json_payload['frameworks']})
        )
        db.session.commit()
    except DataError as e:
        db.session.rollback()
        abort(400, "Invalid framework")
    except IntegrityError as e:
        db.session.rollback()
        abort(400, "Slug '{}' already in use".format(json_payload["frameworks"]["slug"]))

    return jsonify(frameworks=framework.serialize())


@main.route('/frameworks/<string:framework_slug>', methods=['GET'])
def get_framework(framework_slug):
    framework = Framework.query.filter(
        Framework.slug == framework_slug
    ).first_or_404()

    return jsonify(frameworks=framework.serialize())


@main.route('/frameworks/<framework_slug>', methods=['POST'])
def update_framework(framework_slug):
    attribute_whitelist = {
        'status': 'status',
        'clarificationQuestionsOpen': 'clarification_questions_open',
        'frameworkAgreementDetails': 'framework_agreement_details'
    }

    updater_json = validate_and_return_updater_request()
    framework = Framework.query.filter(
        Framework.slug == framework_slug
    ).first_or_404()

    json_payload = get_json_from_request()
    json_has_required_keys(json_payload, ['frameworks'])

    if not json_payload['frameworks']:
        abort(400, "Framework update expects a payload")

    invalid_keys = (set(json_payload['frameworks'].keys()) - set(attribute_whitelist.keys()))
    if invalid_keys:
        abort(400, "Invalid keys for framework update: '{}'".format("', '".join(invalid_keys)))

    if 'frameworkAgreementDetails' in json_payload['frameworks']:
        # all frameworkAgreementDetails keys must be present or the update will fail
        validate_framework_agreement_details_data(
            json_payload['frameworks']['frameworkAgreementDetails'],
            enforce_required=True
        )

    for whitelisted_key, value in attribute_whitelist.items():
        if whitelisted_key in json_payload['frameworks']:
            setattr(framework, value, json_payload['frameworks'][whitelisted_key])

    try:
        db.session.add(framework)
        db.session.add(
            AuditEvent(
                audit_type=AuditTypes.framework_update,
                db_object=framework,
                user=updater_json['updated_by'],
                data={'update': json_payload['frameworks']})
        )
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        abort(400, "Database Error: {}".format(e))

    return jsonify(frameworks=framework.serialize())


@main.route('/frameworks/<string:framework_slug>/stats', methods=['GET'])
def get_framework_stats(framework_slug):
    framework = Framework.query.filter(
        Framework.slug == framework_slug
    ).first_or_404()

    seven_days_ago = datetime.datetime.utcnow() + datetime.timedelta(-7)

    has_completed_drafts_query = db.session.query(
        DraftService.supplier_id, func.min(DraftService.id)
    ).filter(
        DraftService.framework_id == framework.id,
        DraftService.status == 'submitted'
    ).group_by(
        DraftService.supplier_id
    ).subquery('completed_drafts')

    drafts_alias = orm.aliased(DraftService, has_completed_drafts_query)

    def label_columns(labels, query):
        return [
            dict(zip(labels, item))
            for item in sorted(query, key=lambda x: list(map(str, x)))
        ]

    is_declaration_complete = case([
        (SupplierFramework.declaration['status'].astext == 'complete', True)
    ], else_=False)

    return jsonify({
        'services': label_columns(
            ['status', 'lot', 'declaration_made', 'count'],
            db.session.query(
                DraftService.status, Lot.slug, is_declaration_complete, func.count()
            ).outerjoin(
                SupplierFramework, DraftService.supplier_id == SupplierFramework.supplier_id
            ).join(
                Lot, DraftService.lot_id == Lot.id
            ).group_by(
                DraftService.status, Lot.slug, is_declaration_complete
            ).filter(
                SupplierFramework.framework_id == framework.id,
                DraftService.framework_id == framework.id,
                SupplierFramework.declaration.isnot(None)
            ).all()
        ),
        'supplier_users': label_columns(
            ['recent_login', 'count'],
            db.session.query(
                User.logged_in_at > seven_days_ago, func.count()
            ).filter(
                User.role == 'supplier'
            ).group_by(
                User.logged_in_at > seven_days_ago
            ).all()
        ),
        'interested_suppliers': label_columns(
            ['declaration_status', 'has_completed_services', 'count'],
            db.session.query(
                SupplierFramework.declaration['status'].astext,
                drafts_alias.supplier_id.isnot(None), func.count()
            ).select_from(
                Supplier
            ).join(
                SupplierFramework
            ).outerjoin(
                drafts_alias
            ).filter(
                SupplierFramework.framework_id == framework.id,
                SupplierFramework.declaration.isnot(None)
            ).group_by(
                SupplierFramework.declaration['status'].astext, drafts_alias.supplier_id.isnot(None)
            ).all()
        )
    })


@main.route('/frameworks/<string:framework_slug>/suppliers', methods=['GET'])
def get_framework_suppliers(framework_slug):
    framework = Framework.query.filter(
        Framework.slug == framework_slug
    ).first_or_404()

    # we're going to need an "alias" for the current_framework_agreement join
    # so that we can refer to it in later clauses
    cfa = orm.aliased(SupplierFramework._CurrentFrameworkAgreement)
    supplier_frameworks = SupplierFramework.query.outerjoin(
        cfa, SupplierFramework.current_framework_agreement
    ).options(
        orm.contains_eager(
            SupplierFramework.current_framework_agreement, alias=cfa
        )
    )
    # now we can use the alias `cfa` to refer to the joinedload that
    # SupplierFramework.current_framework_agreement would usually cause

    supplier_frameworks = supplier_frameworks.filter(
        SupplierFramework.framework_id == framework.id
    ).order_by(
        # Listing agreements is something done for Admin only (suppliers only retrieve their individual agreements)
        # and CCS always want to work from the oldest returned date to newest, so order by ascending date
        cfa.signed_agreement_returned_at.asc().nullsfirst(),
        SupplierFramework.supplier_id,
    )

    # endpoint has evolved a bit of an oddly designed interface here in that the two filterable parameters aren't
    # really orthogonal. implementing them as such anyway for clarity.

    agreement_returned = request.args.get('agreement_returned')
    if agreement_returned is not None:
        supplier_frameworks = supplier_frameworks.filter(
            # using the not-nullable FrameworkAgreement.id as a proxy for testing row null-ness
            cfa.id.isnot(None) if convert_to_boolean(agreement_returned) else cfa.id.is_(None)
        )

    status = request.args.get('status')
    if status is not None:
        supplier_frameworks = supplier_frameworks.filter(
            cfa.status.in_(status.split(","))
        )

    with_declarations = convert_to_boolean(request.args.get("with_declarations", "true"))

    return jsonify(supplierFrameworks=[
        supplier_framework.serialize(
            with_users=False,
            with_declaration=with_declarations,
        ) for supplier_framework in supplier_frameworks
    ])


@main.route('/frameworks/<string:framework_slug>/interest', methods=['GET'])
def get_framework_interest(framework_slug):
    framework = Framework.query.filter(
        Framework.slug == framework_slug
    ).first_or_404()

    supplier_frameworks = SupplierFramework.query.filter(
        SupplierFramework.framework_id == framework.id
    ).order_by(SupplierFramework.supplier_id).all()

    supplier_ids = [supplier_framework.supplier_id for supplier_framework in supplier_frameworks]

    return jsonify(interestedSuppliers=supplier_ids)
