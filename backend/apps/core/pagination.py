from rest_framework.pagination import PageNumberPagination


class BoundedPageNumberPagination(PageNumberPagination):
    """Default pagination for all API list endpoints.

    Every endpoint using this class caps page size at max_page_size, so no
    endpoint can be made to return an entire table in one response.
    """

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
