from django.conf.urls import url, include
from django.contrib.auth import views as auth_views

from . import views

urlpatterns = [
    url(r'^$', views.index, {}, 'user'),

    url(r'^log-in/$', auth_views.LoginView.as_view(template_name='user/login.html'), name='auth_log_in'),
    url(r'^log-out/$', auth_views.LogoutView.as_view(template_name='user/logout.html'), name='auth_log_out'),

    url(r'^password/reset/$', auth_views.PasswordResetView.as_view(
        success_url='/user/password/reset/done/',
        template_name='user/registration/password_reset_form.html',
        email_template_name='user/registration/password_reset_email.html',
        subject_template_name='user/registration/password_reset_subject.txt',
    ), name='password_reset'),
    url(r'^password/reset/done/$', auth_views.PasswordResetDoneView.as_view(
        template_name='user/registration/password_reset_done.html',
    ), name='password_reset_done'),
    url(r'^password/reset/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$', auth_views.PasswordResetConfirmView.as_view(
        success_url='/user/password/done/',
        template_name='user/registration/password_reset_confirm.html',
    ), name='password_reset_confirm'),
    url(r'^password/done/$', auth_views.PasswordResetCompleteView.as_view(
        template_name='user/registration/password_reset_complete.html',
    ), name='password_reset_complete'),

    url(r'^sign-up/$', views.signup, {}, 'registration_register'),

    url(r'^edit/profile/$', views.editprofile, {}, 'editprofile'),
    url(r'^edit/ratings/$', views.editratings, {}, 'editratings'),
    ]
