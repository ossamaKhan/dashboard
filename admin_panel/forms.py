from django import forms
from marketing.models import SiteData, UserProfile

class SiteDataForm(forms.ModelForm):
    class Meta:
        model = SiteData
        fields = '__all__'
        widgets = {
            'franchise': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Enter franchise name'}),
            'month': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Month number (1-12)'}),
            'key': forms.NumberInput(attrs={'class': 'form-input'}),
            'id_2g': forms.TextInput(attrs={'class': 'form-input'}),
            'id_3g': forms.TextInput(attrs={'class': 'form-input'}),
            'id_4g': forms.TextInput(attrs={'class': 'form-input'}),
            'technology': forms.Select(attrs={'class': 'form-input'}),
            'business_unit': forms.TextInput(attrs={'class': 'form-input'}),
            'region': forms.TextInput(attrs={'class': 'form-input'}),
            'commercial_district': forms.TextInput(attrs={'class': 'form-input'}),
            'cl_status': forms.TextInput(attrs={'class': 'form-input'}),
            'usf_status': forms.Select(attrs={'class': 'form-input'}, choices=[('', 'Select'), ('Active', 'Active'), ('Inactive', 'Inactive')]),
            'latitude': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'pta_district': forms.TextInput(attrs={'class': 'form-input'}),
            'site_status': forms.Select(attrs={'class': 'form-input'}, choices=[('', 'Select'), ('Active', 'Active'), ('Inactive', 'Inactive')]),
            'site_type': forms.TextInput(attrs={'class': 'form-input'}),
            'feb_26': forms.TextInput(attrs={'class': 'form-input'}),
            'arm': forms.TextInput(attrs={'class': 'form-input'}),
            'fca': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'bvs': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'act_90d': forms.NumberInput(attrs={'class': 'form-input'}),
            'act_30d': forms.NumberInput(attrs={'class': 'form-input'}),
            'act_90d_4g': forms.NumberInput(attrs={'class': 'form-input'}),
            'hvc_base': forms.NumberInput(attrs={'class': 'form-input'}),
            'tot_revn_amt': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'bvs_retailer': forms.NumberInput(attrs={'class': 'form-input'}),
            'evc_retailer': forms.NumberInput(attrs={'class': 'form-input'}),
            'minutes_outgoing': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'minutes_incoming': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'volume_gbs': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'data_ntwrk_vol_4g': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'fca_adjusted': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'tot_revival': forms.NumberInput(attrs={'class': 'form-input'}),
            'gross_churn': forms.NumberInput(attrs={'class': 'form-input'}),
            'net_add': forms.NumberInput(attrs={'class': 'form-input'}),
            'avg_dly_act': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'act_recharger': forms.NumberInput(attrs={'class': 'form-input'}),
            'm0_revn': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'mnp_fca': forms.NumberInput(attrs={'class': 'form-input'}),
            'handset_4g': forms.NumberInput(attrs={'class': 'form-input'}),
            'rchrg_face_value_mtd': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'pp_rechar_face_val_mtd': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'prepaid_dgtl_amount': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'postpaid_dgtl_amount': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'conventional_recharge': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'total_recharge': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
            'digi_recharge': forms.NumberInput(attrs={'class': 'form-input', 'step': 'any'}),
        }

class UserProfileForm(forms.ModelForm):
    username = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=False)
    last_name = forms.CharField(max_length=30, required=False)
    
    class Meta:
        model = UserProfile
        fields = ['phone', 'designation', 'department', 'region', 'employee_id', 'bio', 'picture']
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Phone number'}),
            'designation': forms.Select(attrs={'class': 'form-input'}),
            'department': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Department'}),
            'region': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Region'}),
            'employee_id': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Employee ID'}),
            'bio': forms.Textarea(attrs={'class': 'form-input', 'rows': 4, 'placeholder': 'Bio'}),
            'picture': forms.FileInput(attrs={'class': 'form-input'}),
        }