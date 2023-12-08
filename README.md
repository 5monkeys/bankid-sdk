# BankID-SDK

A Python SDK for BankID

## Getting started

### Actions

In order to interact with the `auth` and `sign` BankID order flows, `bankid-sdk`
is expected to be configured with actions. An action essentially declares two
callbacks that will be invoked during two different phases of order flows.

1. The first callback is named `initialize` and will be invoked just before any
  order is initialised via the BankID web API.
2. The second callback is named `finalize` and will be invoked as soon as a
  _completed_ order has been retrieved from the BankID web API.

Implementing actions will be your main entrypoint for incorporating your
required business logic with the BankID order flows.

#### Action for a BankID authentication order

To implement an action designated for an authentication order you would create a
subclass of `bankid_sdk.AuthAction`.

#### Action for a BankID sign order

To implement an action designated for a sign order you would create a subclass
of `bankid_sdk.SignAction`.

### Configuration

`bankid-sdk` needs to be configured before it can work properly. Configuration
is done by calling `bankid_sdk.configure(...)` with relevant values.

```python
import bankid_sdk
from typing import Any


class BankIDLoginAction(bankid_sdk.AuthAction):
    name = "LOGIN"

    def initialize(
        self, request: Any, context: Any
    ) -> tuple[bankid_sdk.UserAuthData, dict[str, Any] | None]:
        auth_data = bankid_sdk.UserAuthData(
            visible="Login with BankID", non_visible=None, visible_format=None
        )
        return auth_data, {}

    def finalize(
        self, response: bankid_sdk.CompleteCollect, request: Any, context: Any
    ) -> None:
        # Do login
        ...


bankid_sdk.configure(
    api_base_url="https://appapi2.test.bankid.com/",
    storage=...,
    actions=[BankIDLoginAction],
    certificate=(
        "path/to/bankid/ssl/cert.pem",
        "path/to/bankid/ssl/private_key.pem",
    ),
    ca_cert="path/to/bankid/root.crt",
)
```

## Usage with Django

The `bankid-sdk` package includes a couple of contributed pieces for
[Django](https://docs.djangoproject.com/):

- Three predeclared and configurable Django views, all accepting a JSON request body:
  - `auth`
  - `check`
  - `cancel`
- A storage backend utilising Django's cache, called `CacheStorage`

### Example setup

To quickly get up and running with your BankID integration with Django you can register
the predeclared views and configure `bankid-sdk` to store results in the cache.

#### Register the Django views from `bankid-sdk`

```python
# urls.py
from bankid_sdk.contrib.django import rest
from django.urls import path

urlpatterns = [
    path("auth/", rest.auth, name="auth"),
    path("check/", rest.check, name="check"),
    path("cancel/", rest.cancel, name="cancel"),
]
```

#### An example login action

```python
from typing import Any

import bankid_sdk
from django.contrib.auth import authenticate, login


class BankIDLoginAction(bankid_sdk.AuthAction):
    name = "LOGIN"

    def initialize(
        self, request: Any, context: Any
    ) -> tuple[bankid_sdk.UserAuthData, dict[str, Any] | None]:
        auth_data = bankid_sdk.UserAuthData(
            visible="Login to my site", non_visible=None, visible_format=None
        )
        return auth_data, context

    def finalize(
        self, response: bankid_sdk.CompleteCollect, request: Any, context: Any
    ) -> None:
        user = authenticate(
            request, personal_number=response.completion_data.user.personal_number
        )
        if user is None:
            raise bankid_sdk.FinalizeFailed(detail="No registered user found")

        login(request, user)
```

The above `authenticate` call from Django requires [writing a custom
authentication backend](https://docs.djangoproject.com/en/dev/topics/auth/customizing/#writing-an-authentication-backend)
that expects a `personal_number` keyword argument. As such you would probably
also need to store a personal number in relation to your user.

#### Configuring

```python
import bankid_sdk
from bankid_sdk.contrib.django.storage import CacheStorage

bankid_sdk.configure(
    api_base_url="https://appapi2.test.bankid.com/",
    storage=CacheStorage(),
    actions=[BankIDLoginAction],
    certificate=(
        "path/to/bankid/ssl/cert.pem",
        "path/to/bankid/ssl/private_key.pem",
    ),
    ca_cert="path/to/bankid/root.crt",
)
```

### More about the included Django views

All endpoints expects a `POST` request with JSON content type body.

#### `auth`

On success it initiates a new authentication order.

#### `check`

Checks for a result regarding an authentication or sign order.

#### `cancel`

Cancels an ongoing sign or auth order.
