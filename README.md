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
from typing import Any

import bankid_sdk


class BankIDLoginAction(bankid_sdk.AuthAction):
    """
    My fancy action that logs in a user.
    """
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

- Views for handling the BankID order flows
- A storage backend utilising Django's cache, called `CacheStorage`

### Sync flow

For synchronous flow there are three predeclared and configurable Django
views, all accepting a JSON request body:

- `auth`
- `check`
- `cancel`

### Async flow

There's an async flow which uses `StreamingHttpResponse` to stream events following
[server sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events#event_stream_format)
interface and requires django to being run with an ASGI server.

When using the async flow there's no need for the client to call the `check`
endpoint this is done automatically by the async view. An ongoing bankid auth
order can be continued by supplying the `transation_id` from the original call
to `async_auth`

- `async_auth`

### Example setup

To quickly get up and running with your BankID integration with Django you can register
the predeclared JSON based views and configure `bankid-sdk` to store results in the
cache.

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
# async auth flow
urlpatterns = [
    path("async_auth/", rest.async_auth, name="async_auth"),
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

_Note: with the async flow the methods should use the `async def` declaration_

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

#### `async_auth`

Works like the `auth` and `check` baked into the same view but returns a
`StreamingHttpResponse` and streams events to give the status of the order and
new QR codes.

**Important to note**: the async view is using POST method and therefore the
browser builtin [EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
will not work as it's only compatible with GET requests.

Since one might potentially want to add custom context data holding
sensitive/personal information, email etc we don't want to use a GET request as
query string parameters could be logged in various places.

Here are two JavaScript implementations for POST method SSE:

- [Using fetch API](https://medium.com/@david.richards.tech/sse-server-sent-events-using-a-post-request-without-eventsource-1c0bd6f14425)
- [Using XMLHttpRequest API](https://solovyov.net/blog/2023/eventsource-post/)

These are the events that can be received from the async view:

- auth - this is the first event sent when a new auth order is initiated.
Attached data contains the `transaction_id` and and `auto_start_token`
- pending
- complete
- failed

Together with the event there is data that is json encoded.
These data attributes may be included in that data:

- hint_code (bankid auth failure see
[BankID API documentation](https://www.bankid.com/en/utvecklare/guider/teknisk-integrationsguide/graenssnittsbeskrivning/collect))
- detail (error message from raised `FinalizeFailed` in finalize method or
validation error)
- order (only set for `complete` event)
- finalize_data (only set for `complete` event if `finalize` method returns
data)
