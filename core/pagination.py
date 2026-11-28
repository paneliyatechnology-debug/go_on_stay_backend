from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from core.url_helpers import to_browser_safe_url


class StandardPageNumberPagination(PageNumberPagination):
    """
    Standard GoOnStay Server-Side Pagination
    - Default page size: 10 records
    - Allowed custom page size query parameter: ?page_size=...
    - Maximum allowed page size: 100 records
    - Response structure:
      {
        "count": <total_matching_records>,
        "next": <next_page_url_or_null>,
        "previous": <previous_page_url_or_null>,
        "results": [<records_for_current_page>]
      }
    - Defense-in-depth: Strips internal backend IPs and ports from next/previous links,
      returning clean same-origin relative URLs or configured public domain URLs.
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_next_link(self):
        raw_link = super().get_next_link()
        return to_browser_safe_url(raw_link, self.request)

    def get_previous_link(self):
        raw_link = super().get_previous_link()
        return to_browser_safe_url(raw_link, self.request)

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data
        })

