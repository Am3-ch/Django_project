from django import forms

from .models import Post


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['kind', 'title', 'content']
        widgets = {
            'kind': forms.RadioSelect,
        }
