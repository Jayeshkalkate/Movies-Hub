from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django import forms

from .models import (
    CustomUser,
    Category,
    TelegramMovie,
)


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'password1', 'password2')


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = CustomUser
        fields = ('username', 'email')


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description', 'icon']
        widgets = {
            'name': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'e.g., Action, Comedy, Drama'
                }
            ),
        }


# =====================================================
# TELEGRAM MOVIE UPLOAD FORM
# =====================================================

class TelegramMovieUploadForm(forms.ModelForm):
    movie_file = forms.FileField(
        label="Video file",
        required=True
    )

    class Meta:
        model = TelegramMovie
        fields = [
            'title',
            'content_type',
            'category',
            'year',
            'quality',
            'language',
            'description',
            'poster',
            'duration',
            'imdb_rating',
            'season',
            'episode',
            'tags',
            'is_featured',
        ]

        widgets = {
            'description': forms.Textarea(
                attrs={
                    'rows': 3,
                    'class': 'form-control'
                }
            ),
            'tags': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'action, thriller, bollywood'
                }
            ),
        }
        
