class LoginView(APIView):
    # FIX: explicitly public. Previously this view had no authentication_classes
    # set, so it inherited the global DEFAULT_AUTHENTICATION_CLASSES
    # (identity.authentication.JWTAuthentication). If a request to this
    # endpoint carried a stale/invalid Authorization header — which the
    # frontend was attaching unconditionally before its own fix above — DRF
    # would reject the request with 401 before this view's post() ever ran,
    # meaning the email/password in the body were never actually checked.
    # A login endpoint must always be reachable regardless of what auth
    # state (valid, expired, or garbage) the caller happens to be carrying.
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        if not request.data or not email or not password:
            return Response({"error": "bad request"}, status=status.HTTP_400_BAD_REQUEST)
        identity = authenticate(request=request, username=email, password=password)
        if identity is not None:
            if identity.email_verified == False:
                return Response(
                    {"user": identity.id, "error": "email not verified"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            try:
                code = generateAuthCode(identity)
            except IntegrityError:
                return Response({"error": "an error occurred"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except DatabaseError:
                return Response({"error": "an error occurred"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            login(request, identity)
            return Response(
                {
                    "user": {
                        "id": identity.id,
                        "first_name": f"{identity.first_name}",
                        "last_name": f"{identity.last_name}",
                    },
                    "detail": "login successfull",
                    "auth_code": code,
                },
                status=status.HTTP_200_OK,
            )
        return Response({"error": "invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
