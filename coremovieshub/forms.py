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
        fields = ("username", "email", "password1", "password2")


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = CustomUser
        fields = ("username", "email")


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description", "icon"]

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., Action, Comedy, Drama",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": "form-control",
                }
            ),
        }


# =====================================================
# TELEGRAM MOVIE UPLOAD FORM
# =====================================================

class TelegramMovieUploadForm(forms.ModelForm):
    movie_file = forms.FileField(
        label="Video File",
        required=True,
        help_text="Upload MP4, MKV, AVI, MOV or WEBM video file (max 2GB).",
    )

    class Meta:
        model = TelegramMovie

        fields = [
            "title",
            "content_type",
            "category",
            "year",
            "quality",
            "language",
            "description",
            "poster",
            "duration",
            "imdb_rating",
            "season",
            "episode",
            "tags",
            "is_featured",
        ]

        widgets = {
            "title": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "content_type": forms.Select(
                attrs={"class": "form-select"}
            ),
            "category": forms.Select(
                attrs={"class": "form-select"}
            ),
            "year": forms.NumberInput(
                attrs={"class": "form-control"}
            ),
            "quality": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "language": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "class": "form-control",
                }
            ),
            "duration": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "imdb_rating": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.1",
                }
            ),
            "season": forms.NumberInput(
                attrs={"class": "form-control"}
            ),
            "episode": forms.NumberInput(
                attrs={"class": "form-control"}
            ),
            "tags": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "action, thriller, bollywood",
                }
            ),
            "is_featured": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }

    def clean_movie_file(self):
        file = self.cleaned_data.get("movie_file")

        if not file:
            raise forms.ValidationError(
                "Please select a video file."
            )

        allowed_extensions = [
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
            ".webm",
        ]

        filename = file.name.lower()

        if not any(
            filename.endswith(ext)
            for ext in allowed_extensions
        ):
            raise forms.ValidationError(
                "Only MP4, MKV, AVI, MOV and WEBM files are allowed."
            )

        # Prevent empty uploads
        if file.size == 0:
            raise forms.ValidationError(
                "Uploaded file is empty."
            )

        # 2 GB limit
        max_size = 2 * 1024 * 1024 * 1024

        if file.size > max_size:
            raise forms.ValidationError(
                "Video file exceeds the 2GB upload limit."
            )

        return file

    def clean_imdb_rating(self):
        rating = self.cleaned_data.get("imdb_rating")

        if rating is not None:
            if rating < 0 or rating > 10:
                raise forms.ValidationError(
                    "IMDb rating must be between 0 and 10."
                )

        return rating