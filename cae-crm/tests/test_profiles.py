import io

from PIL import Image

from conftest import ADMIN, MEMBER, query

PROFILE = {"name": ADMIN[0], "job_title": "Sales director", "department": "Sales", "phone": "07700 900123",
           "location": "Leeds", "linkedin": "linkedin.com/in/test-admin", "bio": "Looks after key accounts."}


def image_file(size=(800, 600), fmt="PNG", exif_gps=False):
    buf = io.BytesIO()
    img = Image.new("RGB", size, (20, 120, 140))
    kwargs = {}
    if exif_gps:
        exif = Image.Exif()
        exif[0x8825] = {1: "N", 2: (51.0, 30.0, 0.0)}  # GPSInfo
        kwargs["exif"] = exif
    img.save(buf, fmt, **kwargs)
    buf.seek(0)
    return buf


def save(client, path="/account/profile", photo=None, **changes):
    data = {"csrf": client.csrf, **PROFILE, **changes}
    if photo is not None:
        data["photo"] = (photo, "me.png")
    return client.post(path, data=data, content_type="multipart/form-data")


def user_id(app, email):
    return query(app, "SELECT id FROM users WHERE email=?", email)[0][0]


def test_profile_saves_and_shows_on_team_and_profile_pages(app, client, member_client):
    assert save(client).status_code == 302
    row = query(app, "SELECT job_title, phone, linkedin, bio FROM users WHERE email=?", ADMIN[1])[0]
    assert tuple(row) == ("Sales director", "+44 7700 900123", "https://linkedin.com/in/test-admin",
                          "Looks after key accounts.")
    team = member_client.get("/team").get_data(as_text=True)
    assert "Sales director" in team
    profile = member_client.get(f"/team/{user_id(app, ADMIN[1])}").get_data(as_text=True)
    assert "Looks after key accounts." in profile and "Open deals" in profile
    assert "Manage access" not in profile  # members can't manage other people


def test_profile_rejects_bad_values(client):
    resp = save(client, phone="12345", linkedin="https://evil.example/in/x", bio="x" * 501, name=" ")
    assert resp.status_code == 422
    page = resp.get_data(as_text=True)
    for message in ("Enter a UK number", "Enter a LinkedIn profile link", "Keep it to 500 characters", "Enter a name"):
        assert message in page


def test_photo_is_resized_stripped_and_private_to_the_workspace(app, client, rival):
    assert save(client, photo=image_file(exif_gps=True)).status_code == 302
    me = user_id(app, ADMIN[1])
    resp = client.get(f"/team/{me}/photo")
    assert resp.status_code == 200 and resp.mimetype == "image/webp"
    img = Image.open(io.BytesIO(resp.data))
    assert img.size == (256, 256)
    assert not img.getexif().get(0x8825)  # no GPS data left
    assert f"/team/{me}/photo?v=" in client.get("/pipeline").get_data(as_text=True)  # owner avatars use it
    assert rival.get(f"/team/{me}/photo").status_code == 404
    assert rival.get(f"/team/{me}").status_code == 404


def test_photo_can_be_removed_and_junk_is_refused(app, client):
    save(client, photo=image_file())
    assert save(client, photo=io.BytesIO(b"not an image at all")).status_code == 422
    assert query(app, "SELECT photo IS NOT NULL FROM users WHERE email=?", ADMIN[1])[0][0]
    save(client, remove_photo="on")
    assert not query(app, "SELECT photo IS NOT NULL FROM users WHERE email=?", ADMIN[1])[0][0]


def test_renaming_yourself_keeps_your_records(app, client):
    owned = query(app, "SELECT COUNT(*) FROM deals WHERE workspace_id=? AND owner=?", app.ws, ADMIN[0])[0][0]
    assert owned
    save(client, name="Test Admin-Jones")
    assert query(app, "SELECT COUNT(*) FROM deals WHERE workspace_id=? AND owner=?", app.ws, "Test Admin-Jones")[0][0] == owned
    assert not query(app, "SELECT COUNT(*) FROM deals WHERE workspace_id=? AND owner=?", app.ws, ADMIN[0])[0][0]


def test_admins_edit_other_profiles_and_members_cannot(app, client, member_client):
    member = user_id(app, MEMBER[1])
    admin = user_id(app, ADMIN[1])
    resp = save(client, f"/team/{member}/edit", name=MEMBER[0], job_title="Support lead")
    assert resp.status_code == 302
    assert query(app, "SELECT job_title FROM users WHERE id=?", member)[0][0] == "Support lead"
    assert save(member_client, f"/team/{admin}/edit", job_title="Hacked").status_code == 403
    assert query(app, "SELECT job_title FROM users WHERE id=?", admin)[0][0] != "Hacked"
    assert "Manage access" in client.get(f"/team/{member}").get_data(as_text=True)
