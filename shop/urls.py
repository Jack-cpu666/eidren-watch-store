from django.urls import path

from . import views

app_name = "shop"

urlpatterns = [
    path("", views.home, name="home"),
    path("watches/", views.catalog, name="catalog"),
    path("watches/<slug:slug>/", views.product_detail, name="product_detail"),
    path("bag/", views.cart, name="cart"),
    path("bag/add/<int:product_id>/", views.cart_add, name="cart_add"),
    path("bag/update/<int:product_id>/", views.cart_update, name="cart_update"),
    path("bag/remove/<int:product_id>/", views.cart_remove, name="cart_remove"),
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/success/", views.checkout_success, name="checkout_success"),
    path("checkout/cancel/", views.checkout_cancel, name="checkout_cancel"),
    path("account/", views.account, name="account"),
    path("account/sign-in/", views.account_login, name="account_login"),
    path("account/create/", views.account_register, name="account_register"),
    path("account/sign-out/", views.account_logout, name="account_logout"),
    path("pages/<slug:slug>/", views.page, name="page"),
    path("health/", views.health, name="health"),
    path("webhooks/stripe/", views.stripe_webhook, name="stripe_webhook"),
]
