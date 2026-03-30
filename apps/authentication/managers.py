from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):

    def _create(self, password=None, **fields):
        user = self.model(**fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, phone=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create(password=password, phone=phone, **extra_fields)

    def create_superuser(self, phone, password, **extra_fields):
        extra_fields.update({"is_staff": True, "is_superuser": True, "role": "admin"})
        return self._create(password=password, phone=phone, **extra_fields)