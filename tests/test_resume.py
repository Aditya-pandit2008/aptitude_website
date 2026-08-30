import io


def test_resume_analysis_accepts_uploaded_text_file(client, auth_headers):
    file_data = io.BytesIO(b"Python, Java, SQL, Data Structures\nProject: built analytics dashboard")
    response = client.post(
        "/api/v1/resume/analyze",
        data={
            "resume_file": (file_data, "resume.txt"),
            "job_description": "Backend developer with Python and SQL"
        },
        headers=auth_headers,
        content_type="multipart/form-data"
    )

    assert response.status_code in (200, 201)
    payload = response.get_json()
    assert payload["success"] is True
    assert "analysis" in payload["data"]
