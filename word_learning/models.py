from django.db import models
from django.apps import apps
from django.contrib import auth
from django.core.mail import send_mail
from django.contrib.auth.models import PermissionsMixin
from django.contrib.auth.base_user import AbstractBaseUser
from multiselectfield import MultiSelectField
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.contrib.auth.base_user import BaseUserManager

class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, username, password, **extra_fields):
        """
        Create and save a user with the given email, and password.
        """
        if not email:
            raise ValueError('The given email must be set')
        email = self.normalize_email(email)
        # Lookup the real model class from the global app registry so this
        # manager method can be used in migrations. This is fine because
        # managers are by definition working on the real model.
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, username=username, password=password, **extra_fields)

    def create_superuser(self, email, username, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(email=email,username=username, password=password, **extra_fields)

#migrateするときにエラーが出るなら、settings.pyのINSTALLED_APPSのdjango.contrib.adminをコメントアウトして、migrateし、再度追加することで解決しました
class CustomUser(AbstractBaseUser, PermissionsMixin):
    CEFR_CHOICES = [
        ('A1', 'A1 - Beginner'),
        ('A2', 'A2 - Elementary'),
        ('B1', 'B1 - Intermediate'),
        ('B2', 'B2 - Upper Intermediate'),
        ('C1', 'C1 - Advanced'),
        ('C2', 'C2 - Mastery'),
    ]
    username_validator = UnicodeUsernameValidator()

    username = models.CharField(
        _('username'),
        max_length=150,
        help_text=('Required. 150 characters or fewer. Letters, digits and @/./+/-/_only.'),
        validators=[username_validator],
        error_messages={
            'unique': _("A user with that username already exists."),
        },
    )
    first_name = models.CharField(_('first name'), max_length=150, blank=True)
    last_name = models.CharField(_('last name'), max_length=150, blank=True)
    email = models.EmailField(_('email address'), unique=True)
    is_staff = models.BooleanField(
        _('staff status'),
        default=False,
        help_text = _('Designates whether the user can log into this admin site.')
    )
    is_active = models.BooleanField(
        _('active'),
        default = True,
        help_text=_(
            'Designates whether this user should be treated as active. '
            'Unselect this instead of deleting accounts. '
        ),
    )
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)
    EMAIL_FIELD = 'email'
    USERNAME_FIELD = 'email'

    objects = UserManager()

    cefr = models.CharField(max_length=2, blank=True, null=True, choices=CEFR_CHOICES)

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')

    def clean(self):
        self.email = self.__class__.objects.normalize_email(self.email)
        
    def get_full_name(self):
        full_name = "%s %s" % (self.first_name, self.last_name)
        return full_name.strip()
    
    def get_short_name(self):
        return self.first_name

    def email_user(self, subject, message, from_email=None, **kwargs):
        send_mail(subject, message, from_email, [self.email], **kwargs)
        
class EngWord(models.Model):
    PART_OF_SPEECH_CHOICES = [
        ('noun', 'Noun'),
        ('verb', 'Verb'),
        ('adjective', 'Adjective'),
        ('adverb', 'Adverb'),
        ('pronoun', 'Pronoun'),
        ('preposition', 'Preposition'),
        ('conjunction', 'Conjunction'),
        ('interjection', 'Interjection'),
        ('article', 'Article'),
    ]
    CEFR_CHOICES = [
        ('A1', 'A1 - Beginner'),
        ('A2', 'A2 - Elementary'),
        ('B1', 'B1 - Intermediate'),
        ('B2', 'B2 - Upper Intermediate'),
        ('C1', 'C1 - Advanced'),
        ('C2', 'C2 - Mastery'),
    ]


    eng_word = models.CharField(max_length=30)
    meaning = models.CharField(max_length=300, blank=True, null=True)
    part_of_speech = MultiSelectField(max_length=30, 
                                      choices=PART_OF_SPEECH_CHOICES,
                                      max_choices=9,
                                      blank=True, null=True)
    synonyms = models.ManyToManyField('self', blank=True, null=True)
    antonyms = models.ManyToManyField('self', blank=True, null=True)
    cefr = models.CharField(max_length=2, blank=True, null=True, choices=CEFR_CHOICES)
    star = models.BooleanField(default=False)


    def __str__(self):
        return self.eng_word 
    
class ExampleSentence(models.Model):
    sentence = models.CharField(max_length=60)
    eng_word = models.ForeignKey(EngWord, on_delete=models.CASCADE)

class WrittingQuiz(models.Model):
    quiz = models.CharField(max_length=1000)
    llm_quiz = models.BooleanField(default=False) #True means created by llm
    highest_score = models.PositiveIntegerField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

class WrittingAnswer(models.Model):
    quiz = models.ForeignKey(WrittingQuiz, on_delete=models.CASCADE)
    answer = models.CharField(max_length=10000)
    score = models.PositiveIntegerField(validators=[MinValueValidator(0), MaxValueValidator(100)], blank=True, null=True)
    scored = models.BooleanField(default=False) # If it has not scored, this is false
    comment = models.CharField(max_length=10000, blank=True, null = True)
    created_at = models.DateTimeField(auto_now_add=True)
