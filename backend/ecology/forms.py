from django import forms


class SimulationCleanupConfirmForm(forms.Form):
    token = forms.CharField(widget=forms.HiddenInput, max_length=2000)
    confirm = forms.BooleanField(label="我已核对预览，并确认永久删除这些过期模拟批次及其观测。")
