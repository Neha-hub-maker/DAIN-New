from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.dain import User, UserRole
from app.services.security import hash_password


def register_verify_and_login(client, email="member@du.ac.bd"):
    registration = client.post(
        "/auth/register",
        json={
            "full_name": "Member User",
            "email": email,
            "password": "secure-password-123",
            "department": "CSE",
        },
    )

    assert registration.status_code == 201

    assert client.post(
        "/auth/verify-email",
        json={"token": registration.json()["verification_token"]},
    ).status_code == 200

    login = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "secure-password-123",
        },
    )

    assert login.status_code == 200

    return {
        "Authorization": f"Bearer {login.json()['access_token']}"
    }


def create_admin_headers(client):
    database = SessionLocal()

    try:
        database.add(
            User(
                email="editor@du.ac.bd",
                password_hash=hash_password("secure-password-123"),
                full_name="Editorial Admin",
                role=UserRole.ADMIN,
                is_email_verified=True,
            )
        )

        database.commit()

    finally:
        database.close()

    login = client.post(
        "/auth/login",
        json={
            "email": "editor@du.ac.bd",
            "password": "secure-password-123",
        },
    )

    assert login.status_code == 200

    return {
        "Authorization": f"Bearer {login.json()['access_token']}"
    }


def create_category(client, admin_headers):
    response = client.post(
        "/categories",
        headers=admin_headers,
        json={
            "slug": "academic-test",
            "name": "Academic Test",
            "fields": [
                {
                    "field_key": "publication_link",
                    "label": "Publication link",
                    "field_type": "url",
                    "is_required": True,
                }
            ],
        },
    )

    assert response.status_code == 201

    return response.json()


def create_draft(
    client,
    member_headers,
    category,
    title="Research Achievement",
    field_values=None,
):
    return client.post(
        "/submissions",
        headers=member_headers,
        json={
            "category_id": category["id"],
            "title": title,
            "summary": (
                "This is a sufficiently detailed description of the "
                "achievement for DAIN review."
            ),
            "field_values": field_values or [],
        },
    )


def test_submission_completeness_warning_does_not_block_submission(client):
    member_headers = register_verify_and_login(client)

    category = create_category(
        client,
        create_admin_headers(client),
    )

    draft = create_draft(
        client,
        member_headers,
        category,
    )

    assert draft.status_code == 201

    submitted = client.post(
        f"/submissions/{draft.json()['id']}/submit",
        headers=member_headers,
    )

    assert submitted.status_code == 200

    completeness = next(
        item
        for item in submitted.json()["results"]
        if item["check_type"] == "completeness"
    )

    assert completeness["status"] == "warning"

    assert (
        completeness["details"]["missing_required_fields"][0]["field_key"]
        == "publication_link"
    )


def test_duplicate_title_is_flagged_for_review(client):
    member_headers = register_verify_and_login(client)

    category = create_category(
        client,
        create_admin_headers(client),
    )

    first = create_draft(
        client,
        member_headers,
        category,
        title="National Research Award",
    )

    assert client.post(
        f"/submissions/{first.json()['id']}/submit",
        headers=member_headers,
    ).status_code == 200

    second = create_draft(
        client,
        member_headers,
        category,
        title="National Research Award",
    )

    submitted = client.post(
        f"/submissions/{second.json()['id']}/submit",
        headers=member_headers,
    )

    duplicate = next(
        item
        for item in submitted.json()["results"]
        if item["check_type"] == "duplicate_detection"
    )

    assert duplicate["status"] == "warning"
    assert duplicate["details"]["potential_matches"]


def test_editor_can_approve_and_generate_public_media_package(client):
    member_headers = register_verify_and_login(client)

    admin_headers = create_admin_headers(client)

    category = create_category(
        client,
        admin_headers,
    )

    required_field = category["field_definitions"][0]

    draft = create_draft(
        client,
        member_headers,
        category,
        field_values=[
            {
                "field_definition_id": required_field["id"],
                "value": {
                    "url": "https://example.org/paper"
                },
            }
        ],
    )

    submission_id = draft.json()["id"]

    # Submit the achievement for editorial review.
    assert client.post(
        f"/submissions/{submission_id}/submit",
        headers=member_headers,
    ).status_code == 200

    # The editor must claim the submission before creating a review.
    claim = client.post(
        f"/submissions/{submission_id}/claim",
        headers=admin_headers,
    )

    assert claim.status_code == 200

    # The claimed editor can now approve the submission.
    review = client.post(
        f"/submissions/{submission_id}/reviews",
        headers=admin_headers,
        json={
            "decision": "approved",
            "notes": "Ready.",
        },
    )

    print("REVIEW STATUS:", review.status_code)
    print("REVIEW RESPONSE:", review.text)
    assert review.status_code == 201
    print("REVIEW STATUS:", review.status_code)
    print("REVIEW RESPONSE:", review.text)

    # Generate the public media package after approval.
    package = client.post(
        f"/submissions/{submission_id}/media-package",
        headers=admin_headers,
    )

    assert package.status_code == 201

    # Confirm the generated public page is accessible.
    public_page = client.get(
        package.json()["public_url"]
    )

    assert public_page.status_code == 200
    assert "Research Achievement" in public_page.text


def test_upload_rejects_an_unsupported_file_type(client):
    member_headers = register_verify_and_login(client)

    category = create_category(
        client,
        create_admin_headers(client),
    )

    draft = create_draft(
        client,
        member_headers,
        category,
    )

    response = client.post(
        f"/submissions/{draft.json()['id']}/assets",
        headers=member_headers,
        files={
            "file": (
                "malware.exe",
                b"not an executable",
                "application/octet-stream",
            )
        },
    )
    assert response.status_code == 415