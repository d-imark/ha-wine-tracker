import sqlite3
import images


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE wines (id INTEGER PRIMARY KEY, image TEXT)")
    images.create_images_table(c)
    return c


def _wine(c, image=None):
    cur = c.execute("INSERT INTO wines (image) VALUES (?)", (image,))
    return cur.lastrowid


class TestImagesModule:
    def test_first_image_becomes_default_and_syncs(self):
        c = _conn(); wid = _wine(c)
        iid = images.add_image(c, wid, "scan", "a.jpg")
        imgs = images.list_images(c, wid)
        assert len(imgs) == 1 and imgs[0]["is_default"] == 1 and imgs[0]["id"] == iid
        assert c.execute("SELECT image FROM wines WHERE id=?", (wid,)).fetchone()[0] == "a.jpg"

    def test_second_image_not_default_and_order(self):
        c = _conn(); wid = _wine(c)
        images.add_image(c, wid, "scan", "a.jpg")
        images.add_image(c, wid, "vivino", "b.jpg")
        imgs = images.list_images(c, wid)
        assert [i["filename"] for i in imgs] == ["a.jpg", "b.jpg"]
        assert imgs[1]["is_default"] == 0
        assert imgs[1]["sort_order"] == 1

    def test_invalid_category_raises(self):
        c = _conn(); wid = _wine(c)
        try:
            images.add_image(c, wid, "bogus", "x.jpg")
            assert False, "expected ValueError"
        except ValueError:
            pass

    def test_set_default_is_exclusive(self):
        c = _conn(); wid = _wine(c)
        i1 = images.add_image(c, wid, "scan", "a.jpg")
        i2 = images.add_image(c, wid, "vivino", "b.jpg")
        assert images.set_default(c, wid, i2) is True
        defaults = [i["id"] for i in images.list_images(c, wid) if i["is_default"]]
        assert defaults == [i2]
        assert c.execute("SELECT image FROM wines WHERE id=?", (wid,)).fetchone()[0] == "b.jpg"
        assert images.set_default(c, wid, 9999) is False  # not this wine's image

    def test_remove_default_promotes_next(self):
        c = _conn(); wid = _wine(c)
        i1 = images.add_image(c, wid, "scan", "a.jpg")
        i2 = images.add_image(c, wid, "vivino", "b.jpg")
        fname = images.remove_image(c, wid, i1)
        assert fname == "a.jpg"
        imgs = images.list_images(c, wid)
        assert len(imgs) == 1 and imgs[0]["id"] == i2 and imgs[0]["is_default"] == 1
        assert c.execute("SELECT image FROM wines WHERE id=?", (wid,)).fetchone()[0] == "b.jpg"

    def test_remove_last_clears_wines_image(self):
        c = _conn(); wid = _wine(c)
        i1 = images.add_image(c, wid, "scan", "a.jpg")
        images.remove_image(c, wid, i1)
        assert images.list_images(c, wid) == []
        assert c.execute("SELECT image FROM wines WHERE id=?", (wid,)).fetchone()[0] is None

    def test_migrate_legacy_is_idempotent(self):
        c = _conn(); wid = _wine(c, image="legacy.jpg")
        images.migrate_legacy_images(c)
        images.migrate_legacy_images(c)  # second run must not duplicate
        imgs = images.list_images(c, wid)
        assert len(imgs) == 1
        assert imgs[0]["category"] == "scan" and imgs[0]["is_default"] == 1
        assert imgs[0]["filename"] == "legacy.jpg"

    def test_sync_primary_new_creates_scan_default(self):
        c = _conn(); wid = _wine(c)
        images.sync_primary(c, wid, "", "new.jpg")
        imgs = images.list_images(c, wid)
        assert len(imgs) == 1 and imgs[0]["category"] == "scan" and imgs[0]["is_default"] == 1
        assert c.execute("SELECT image FROM wines WHERE id=?", (wid,)).fetchone()[0] == "new.jpg"

    def test_sync_primary_clear_removes_old(self):
        c = _conn(); wid = _wine(c)
        images.sync_primary(c, wid, "", "old.jpg")
        images.sync_primary(c, wid, "old.jpg", "")
        assert images.list_images(c, wid) == []
        assert c.execute("SELECT image FROM wines WHERE id=?", (wid,)).fetchone()[0] is None
