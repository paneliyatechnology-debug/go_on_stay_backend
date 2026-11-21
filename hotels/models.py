from django.db import models
from django.conf import settings

class Country(models.Model):
    name = models.CharField(max_length=100, unique=True, db_index=True)
    code = models.CharField(max_length=10, unique=True, db_index=True)  # e.g., "IN"
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Countries'

    def __str__(self):
        return f"{self.name} ({self.code})"


class State(models.Model):
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='states')
    name = models.CharField(max_length=100, db_index=True)
    code = models.CharField(max_length=10, blank=True, default='')  # e.g., "GJ", "MH", "RJ", "GA"
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = ('country', 'name')

    def __str__(self):
        return f"{self.name}, {self.country.name}"


class City(models.Model):
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name='cities')
    name = models.CharField(max_length=100, db_index=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = ('state', 'name')
        verbose_name_plural = 'Cities'

    def __str__(self):
        return f"{self.name}, {self.state.name}"


class Area(models.Model):
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='areas')
    name = models.CharField(max_length=150, db_index=True)
    zip_code = models.CharField(max_length=20, blank=True, default='')
    latitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __init__(self, *args, **kwargs):
        if 'pincode' in kwargs:
            kwargs['zip_code'] = kwargs.pop('pincode')
        super().__init__(*args, **kwargs)

    @property
    def pincode(self):
        return self.zip_code

    @pincode.setter
    def pincode(self, val):
        self.zip_code = val or ''

    class Meta:
        ordering = ['name']
        unique_together = ('city', 'name')

    def __str__(self):
        return f"{self.name}, {self.city.name}"


class Amenity(models.Model):
    name = models.CharField(max_length=100, unique=True)
    icon_name = models.CharField(max_length=50, default='CheckCircle')
    category = models.CharField(max_length=50, default='General')

    def __str__(self):
        return self.name

class Hotel(models.Model):
    PROPERTY_TYPE_HOTEL = 'HOTEL'
    PROPERTY_TYPE_RESORT = 'RESORT'
    PROPERTY_TYPE_VILLA = 'VILLA'
    PROPERTY_TYPE_GUEST_HOUSE = 'GUEST_HOUSE'
    PROPERTY_TYPE_HOSTEL = 'HOSTEL'
    PROPERTY_TYPE_APARTMENT = 'APARTMENT'
    PROPERTY_TYPE_HOMESTAY = 'HOMESTAY'
    PROPERTY_TYPE_BOUTIQUE = 'BOUTIQUE_HOTEL'

    PROPERTY_TYPE_CHOICES = (
        (PROPERTY_TYPE_HOTEL, 'Hotel'),
        (PROPERTY_TYPE_RESORT, 'Resort'),
        (PROPERTY_TYPE_VILLA, 'Villa'),
        (PROPERTY_TYPE_GUEST_HOUSE, 'Guest House'),
        (PROPERTY_TYPE_HOSTEL, 'Hostel'),
        (PROPERTY_TYPE_APARTMENT, 'Apartment'),
        (PROPERTY_TYPE_HOMESTAY, 'Homestay'),
        (PROPERTY_TYPE_BOUTIQUE, 'Boutique Hotel'),
    )

    STATUS_DRAFT = 'DRAFT'
    STATUS_SUBMITTED = 'SUBMITTED'
    STATUS_UNDER_REVIEW = 'UNDER_REVIEW'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_SUSPENDED = 'SUSPENDED'
    STATUS_ARCHIVED = 'ARCHIVED'
    STATUS_DELETED = 'DELETED'

    STATUS_CHOICES = (
        (STATUS_DRAFT, 'Draft'),
        (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_UNDER_REVIEW, 'Under Review'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_SUSPENDED, 'Suspended'),
        (STATUS_ARCHIVED, 'Archived'),
        (STATUS_DELETED, 'Deleted'),
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='hotels'
    )
    name = models.CharField(max_length=255)
    description = models.TextField()
    property_type = models.CharField(max_length=30, choices=PROPERTY_TYPE_CHOICES, default=PROPERTY_TYPE_HOTEL)
    
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100, db_index=True)
    state = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, default='India')
    
    area = models.CharField(max_length=150, blank=True, null=True)
    landmark = models.CharField(max_length=200, blank=True, null=True)
    destination = models.CharField(max_length=150, blank=True, null=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=6, blank=True, null=True, default=19.076000)
    longitude = models.DecimalField(max_digits=10, decimal_places=6, blank=True, null=True, default=72.877700)

    star_rating = models.IntegerField(default=4)
    guest_rating = models.DecimalField(max_digits=3, decimal_places=1, default=4.5)
    check_in_time = models.CharField(max_length=20, default='12:00 PM')
    check_out_time = models.CharField(max_length=20, default='11:00 AM')
    
    rules = models.TextField(blank=True, null=True, default='Valid ID required at check-in. Couples allowed.')
    cancellation_policy = models.TextField(blank=True, null=True, default='Free cancellation up to 24 hours prior to check-in date.')
    child_policy = models.TextField(blank=True, null=True, default='Children under 5 stay free without extra bed.')
    pet_policy = models.TextField(blank=True, null=True, default='Pets not allowed unless specified.')
    smoking_policy = models.TextField(blank=True, null=True, default='Non-smoking rooms available.')
    payment_policy = models.TextField(blank=True, null=True, default='Accepts online prepaid bookings via Razorpay.')
    safety_info = models.TextField(blank=True, null=True, default='CCTV cameras, 24/7 security guard, fire extinguishers.')
    nearby_attractions = models.TextField(blank=True, null=True, default='Airport 10km, Railway Station 4km.')

    amenities = models.ManyToManyField(Amenity, related_name='hotels', blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_SUBMITTED)
    is_approved = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(blank=True, null=True)
    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='deleted_hotels')
    rejected_at = models.DateTimeField(blank=True, null=True)
    rejected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='rejected_hotels')
    
    country_rel = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True, related_name='hotels')
    state_rel = models.ForeignKey(State, on_delete=models.SET_NULL, null=True, blank=True, related_name='hotels')
    city_rel = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True, related_name='hotels')
    area_rel = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True, related_name='hotels')

    rejection_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['city']),
            models.Index(fields=['state']),
            models.Index(fields=['latitude', 'longitude']),
            models.Index(fields=['guest_rating']),
            models.Index(fields=['is_deleted', 'is_approved', 'status']),
        ]

    def clean(self):
        super().clean()
        from util.validators import validate_hotel_name, validate_hotel_address
        from django.core.exceptions import ValidationError as DjangoValidationError
        from rest_framework.exceptions import ValidationError as DRFValidationError
        if self.name:
            try:
                self.name = validate_hotel_name(self.name)
            except (DRFValidationError, Exception) as e:
                err_msg = e.detail[0] if hasattr(e, 'detail') and isinstance(e.detail, list) else str(e)
                raise DjangoValidationError({'name': err_msg})
        if self.address:
            try:
                self.address = validate_hotel_address(self.address)
            except (DRFValidationError, Exception) as e:
                err_msg = e.detail[0] if hasattr(e, 'detail') and isinstance(e.detail, list) else str(e)
                raise DjangoValidationError({'address': err_msg})

    def save(self, *args, **kwargs):
        self.clean()
        # Bi-directional location sync:
        if self.area_rel:
            self.area = self.area_rel.name
            if not self.city_rel:
                self.city_rel = self.area_rel.city
        if self.city_rel:
            self.city = self.city_rel.name
            if not self.state_rel:
                self.state_rel = self.city_rel.state
        if self.state_rel:
            self.state = self.state_rel.name
            if not self.country_rel:
                self.country_rel = self.state_rel.country
        if self.country_rel:
            self.country = self.country_rel.name
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.city}) - [{self.status}]"

class HotelImage(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='images')
    image_url = models.URLField(max_length=500, blank=True, null=True)
    image = models.ImageField(upload_to='hotels/images/', blank=True, null=True)
    caption = models.CharField(max_length=200, blank=True, null=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_image_display(self):
        if self.image_url:
            return self.image_url
        if self.image:
            try:
                url = str(self.image.url) if hasattr(self.image, 'url') else str(self.image)
                return url
            except Exception:
                return ''
        return ''

    def __str__(self):
        return f"Image for {self.hotel.name}"

class HotelVerificationDocument(models.Model):
    DOC_BUSINESS_REG = 'BUSINESS_REG'
    DOC_IDENTITY_PROOF = 'IDENTITY_PROOF'
    DOC_TAX_GST = 'TAX_GST'
    DOC_ADDRESS_PROOF = 'ADDRESS_PROOF'

    DOC_TYPE_CHOICES = (
        (DOC_BUSINESS_REG, 'Business Registration'),
        (DOC_IDENTITY_PROOF, 'Government ID Proof'),
        (DOC_TAX_GST, 'GST / Tax Certificate'),
        (DOC_ADDRESS_PROOF, 'Property Ownership / Address Proof'),
    )

    STATUS_PENDING = 'PENDING'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'

    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending Review'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    )

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='verification_documents')
    document_type = models.CharField(max_length=30, choices=DOC_TYPE_CHOICES)
    document_url = models.URLField(max_length=500, blank=True, null=True)
    document_file = models.FileField(upload_to='hotels/documents/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    rejection_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Doc {self.get_document_type_display()} - {self.hotel.name}"

class HotelStaff(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='staff_members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='hotel_staff_roles')
    role_title = models.CharField(max_length=100, default='Front Desk Manager')
    can_manage_bookings = models.BooleanField(default=True)
    can_manage_rooms = models.BooleanField(default=True)
    can_checkin_checkout = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('hotel', 'user')

    def __str__(self):
        return f"Staff {self.user.username} @ {self.hotel.name}"


class DeletedHotelArchive(models.Model):
    hotel = models.OneToOneField(Hotel, on_delete=models.CASCADE, related_name='archive_record')
    hotel_name = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    property_type = models.CharField(max_length=50, blank=True, default='')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='archived_hotels')
    owner_name = models.CharField(max_length=255, blank=True, null=True, default='')
    owner_email = models.CharField(max_length=255, blank=True, null=True, default='')
    owner_phone = models.CharField(max_length=50, blank=True, null=True, default='')

    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='hotel_deletions_performed')
    deleted_by_name = models.CharField(max_length=255, blank=True, null=True, default='')
    deleted_by_role = models.CharField(max_length=50, blank=True, null=True, default='')
    deleted_at = models.DateTimeField(auto_now_add=True)
    deletion_reason = models.TextField(blank=True, null=True, default='')

    # Full JSON snapshot at time of deletion
    snapshot_data = models.JSONField(default=dict, blank=True)

    # Restoration tracking
    is_restored = models.BooleanField(default=False)
    restored_at = models.DateTimeField(null=True, blank=True)
    restored_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['-deleted_at']
        verbose_name = 'Deleted Hotel Archive'
        verbose_name_plural = 'Deleted Hotel Archives'

    def __str__(self):
        return f"Archived: {self.hotel_name} (ID {self.hotel_id}) - Deleted by {self.deleted_by_name}"

