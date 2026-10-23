import pytest


def registration_payload(**overrides):
    payload = {
        "full_name": "Amina Rahman",
        "email": "amina@du.ac.bd",
        "password": "secure-password-123",
        "department": "Computer Science",
    }
    payload.update(overrides)
    return payload


def register_and_verify(client, **overrides):
    registration = client.post("/auth/register", json=registration_payload(**overrides))
    assert registration.status_code == 201
    token = registration.json()["verification_token"]
    assert token
    verification = client.post("/auth/verify-email", json={"token": token})
    assert verification.status_code == 200
    return registration.json()


def test_successful_registration(client):
    response = client.post("/auth/register", json=registration_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "amina@du.ac.bd"
    assert body["user"]["is_email_verified"] is False
    assert body["verification_token"]


def test_invalid_registration_data(client):
    response = client.post("/auth/register", json=registration_payload(password="short"))

    assert response.status_code == 422


def test_non_institutional_email_is_rejected(client):
    response = client.post("/auth/register", json=registration_payload(email="amina@example.com"))

    assert response.status_code == 422
    assert response.json()["detail"] == "A valid institutional email address is required."


@pytest.mark.parametrize("email", [
    "student-2024913694@cs.du.ac.bd",
    "student-19th-2023112801@mis.du.ac.bd",
    "student@another-department.du.ac.bd",
    "student@students.cs.du.ac.bd",
    "student@CS.DU.AC.BD",
])
def test_department_email_can_register_verify_and_log_in(client, email):
    registration = register_and_verify(client, email=email)
    assert registration["user"]["is_email_verified"] is False
    response = client.post("/auth/login", json={"email": email, "password": "secure-password-123"})
    assert response.status_code == 200
    assert response.json()["user"]["email"] == email.lower()
    assert response.json()["user"]["is_email_verified"] is True


@pytest.mark.parametrize("domain", [
    "evildu.ac.bd",
    "csdu.ac.bd",
    "du.ac.bd.example.com",
    "cs.du.ac.bd.example.com",
    "du-ac-bd.com",
    "cs.du.example.com",
])
def test_lookalike_email_domains_cannot_register(client, domain):
    response = client.post("/auth/register", json=registration_payload(email=f"student@{domain}"))
    assert response.status_code == 422
    assert response.json()["detail"] == "A valid institutional email address is required."


def test_successful_login(client):
    register_and_verify(client)

    response = client.post("/auth/login", json={"email": "amina@du.ac.bd", "password": "secure-password-123"})

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_incorrect_password_is_rejected(client):
    register_and_verify(client)

    response = client.post("/auth/login", json={"email": "amina@du.ac.bd", "password": "incorrect-password-123"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_protected_route_accepts_valid_authentication(client):
    register_and_verify(client)
    login = client.post("/auth/login", json={"email": "amina@du.ac.bd", "password": "secure-password-123"})

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})

    assert response.status_code == 200
    assert response.json()["email"] == "amina@du.ac.bd"


def test_protected_route_rejects_missing_authentication(client):
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_unverified_user_cannot_log_in(client):
    client.post("/auth/register", json=registration_payload())

    response = client.post("/auth/login", json={"email": "amina@du.ac.bd", "password": "secure-password-123"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Verify your institutional email before logging in."
