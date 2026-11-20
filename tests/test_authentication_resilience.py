"""
Tests for FlexibleJWTAuthentication and resilient authentication handling.
Guarantees that:
1. Empty / unset Postman tokens (e.g., 'Bearer ') do NOT trigger 500 or bad_authorization_header.
2. Unresolved Postman placeholders ('Bearer {{admin_token}}', 'Bearer null') are treated cleanly as unauthenticated.
3. Raw JWT tokens passed without 'Bearer ' prefix are accepted seamlessly.
4. Valid 'Bearer <token>' authenticates normally.
5. Public endpoints (AllowAny) with empty/malformed Bearer headers are accessible without crashes.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class AuthenticationResilienceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="resilience_test_user",
            email="resilience@goonstay.com",
            password="SecurePassword123!",
            first_name="Resilience",
            last_name="Tester",
            role=User.ROLE_CUSTOMER
        )
        refresh = RefreshToken.for_user(cls.user)
        cls.access_token = str(refresh.access_token)

    def setUp(self):
        self.client = APIClient()

    def test_empty_bearer_header_returns_401_not_bad_authorization_header(self):
        """
        When Postman sends 'Authorization: Bearer ' because {{token}} is empty,
        DRF must return standard 401 Not Authenticated, NOT bad_authorization_header.
        """
        response = self.client.get('/api/users/profile/', HTTP_AUTHORIZATION='Bearer ')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotEqual(
            response.data.get('message'),
            "Authorization header must contain two space-delimited values"
        )
        self.assertEqual(
            response.data.get('message'),
            "Authentication credentials were not provided."
        )

    def test_unresolved_postman_variable_returns_401_cleanly(self):
        """
        When Postman sends 'Authorization: Bearer {{admin_token}}',
        it should be treated as unauthenticated without throwing token decode errors.
        """
        response = self.client.get('/api/users/profile/', HTTP_AUTHORIZATION='Bearer {{admin_token}}')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            response.data.get('message'),
            "Authentication credentials were not provided."
        )

    def test_null_or_undefined_bearer_returns_401_cleanly(self):
        """
        When frontend or test sends 'Authorization: Bearer null' or 'Bearer undefined',
        it should be treated as unauthenticated without throwing token errors.
        """
        for dummy in ['Bearer null', 'Bearer undefined', 'Bearer none']:
            response = self.client.get('/api/users/profile/', HTTP_AUTHORIZATION=dummy)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
            self.assertEqual(
                response.data.get('message'),
                "Authentication credentials were not provided."
            )

    def test_raw_jwt_token_without_bearer_prefix_authenticates_successfully(self):
        """
        If a client sends the raw JWT token without 'Bearer ' prefix,
        FlexibleJWTAuthentication should recognize the 3-part dot structure and authenticate.
        """
        response = self.client.get('/api/users/profile/', HTTP_AUTHORIZATION=self.access_token)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('email'), "resilience@goonstay.com")

    def test_standard_bearer_token_authenticates_successfully(self):
        """
        Standard 'Bearer <token>' must continue to authenticate successfully.
        """
        response = self.client.get('/api/users/profile/', HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get('email'), "resilience@goonstay.com")

    def test_public_endpoint_with_empty_bearer_still_accessible(self):
        """
        A public (AllowAny) endpoint like hotel list should not crash with bad_authorization_header
        even if an empty 'Bearer ' header was sent by mistake.
        """
        response = self.client.get('/api/hotels/', HTTP_AUTHORIZATION='Bearer ')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
