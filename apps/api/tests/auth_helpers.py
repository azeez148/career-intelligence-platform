PASSWORD = "A sufficiently long passphrase!"
ORIGIN = "http://testserver"


async def mutate(client, method, path, data=None):
    if not client.cookies.get("XSRF-TOKEN"):
        assert (await client.get("/api/v1/auth/csrf")).status_code == 204
    return await client.request(
        method,
        "/api/v1" + path,
        json=data if data is not None else {},
        headers={
            "Origin": ORIGIN,
            "X-XSRF-TOKEN": client.cookies.get("XSRF-TOKEN"),
            "Content-Type": "application/json",
        },
    )


async def register_login(client, email="person@example.com"):
    data = {"email": email, "password": PASSWORD}
    registered = await mutate(client, "POST", "/auth/register", {**data, "display_name": "Person"})
    assert registered.status_code == 201, registered.text
    response = await mutate(client, "POST", "/auth/login", data)
    assert response.status_code == 200, response.text
    return response
