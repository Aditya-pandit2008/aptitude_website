def test_company_details_response_shape(client):
    response = client.get("/api/v1/company/details")
    assert response.status_code == 200

    data = response.get_json()
    assert data["success"] is True
    assert "companies" in data["data"]
    assert "tcs" in data["data"]["companies"]
    assert data["data"]["companies"]["tcs"]["name"].startswith("TCS")
