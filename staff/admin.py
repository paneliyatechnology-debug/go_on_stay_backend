from django.contrib import admin
from .models import (
    Department, StaffPermission, StaffProfile, StaffActivityLog,
    StaffNotification, StaffPasswordResetToken, StaffTicketNote, StaffAssignment
)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'created_at')
    search_fields = ('name', 'code')
    list_filter = ('is_active',)


@admin.register(StaffPermission)
class StaffPermissionAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'department', 'action')
    search_fields = ('code', 'name')
    list_filter = ('department', 'action')


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'login_id', 'user', 'department', 'designation', 'status', 'must_change_password', 'created_at')
    search_fields = ('employee_id', 'login_id', 'user__username', 'user__email')
    list_filter = ('status', 'department', 'must_change_password')
    filter_horizontal = ('permissions',)


@admin.register(StaffActivityLog)
class StaffActivityLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'employee_id', 'actor_username', 'action', 'target_entity_type', 'target_entity_id')
    search_fields = ('employee_id', 'actor_username', 'action', 'target_entity_id')
    list_filter = ('action', 'target_entity_type')
    readonly_fields = [f.name for f in StaffActivityLog._meta.fields]


@admin.register(StaffNotification)
class StaffNotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'recipient', 'department', 'notification_type', 'is_read', 'created_at')
    list_filter = ('is_read', 'notification_type', 'department')


@admin.register(StaffTicketNote)
class StaffTicketNoteAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'staff', 'is_internal_only', 'created_at')
    list_filter = ('is_internal_only',)


@admin.register(StaffAssignment)
class StaffAssignmentAdmin(admin.ModelAdmin):
    list_display = ('staff', 'entity_type', 'entity_id', 'is_active', 'assigned_at')
    list_filter = ('entity_type', 'is_active')
