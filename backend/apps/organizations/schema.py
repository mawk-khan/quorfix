from drf_spectacular.extensions import OpenApiAuthenticationExtension


class OrganizationAwareSessionAuthenticationScheme(OpenApiAuthenticationExtension):
    """Tells drf-spectacular how to describe
    OrganizationAwareSessionAuthentication in the generated schema.

    Without this, every view using that authentication class (i.e. every
    authenticated endpoint in the API) logs an "could not resolve
    authenticator ... no OpenApiAuthenticationExtension registered" warning
    during schema generation — registering this class is what silences it.
    Must be imported before schema generation runs; OrganizationsConfig.ready()
    is what guarantees that.
    """

    target_class = "apps.organizations.authentication.OrganizationAwareSessionAuthentication"
    name = "sessionAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": "sessionid",
            "description": (
                "Session-cookie authentication. State-changing requests also require the "
                "X-CSRFToken header, sourced from the csrftoken cookie."
            ),
        }
