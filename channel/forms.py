from django import forms


class ChannelUploadForm(forms.Form):
    file = forms.FileField()