from rest_framework.throttling import UserRateThrottle


class SupportTicketCreateThrottle(UserRateThrottle):
    scope = 'support_ticket_create'


class SupportTicketMessageThrottle(UserRateThrottle):
    scope = 'support_ticket_message'
