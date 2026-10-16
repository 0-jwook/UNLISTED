from musiclib.cleanup import intermediate_names, remove_intermediates, snapshot

BASE = "아이유(IU) - 밤편지"


def _touch(folder, name):
    (folder / name).write_bytes(b"x")


def test_removes_new_thumbnails_and_backup_but_keeps_final_m4a(tmp_path):
    before = snapshot(tmp_path)
    for name in (f"{BASE}.m4a", f"{BASE}.jpg", f"{BASE}.webp", f"{BASE}.m4a_original"):
        _touch(tmp_path, name)
    removed = remove_intermediates(tmp_path, BASE, before, overwrite=False)
    assert sorted(removed) == sorted([f"{BASE}.jpg", f"{BASE}.webp", f"{BASE}.m4a_original"])
    assert (tmp_path / f"{BASE}.m4a").exists()


def test_keeps_backup_that_existed_before_the_run(tmp_path):
    _touch(tmp_path, f"{BASE}.m4a_original")
    before = snapshot(tmp_path)
    _touch(tmp_path, f"{BASE}.m4a")
    _touch(tmp_path, f"{BASE}.jpg")
    removed = remove_intermediates(tmp_path, BASE, before, overwrite=False)
    assert removed == [f"{BASE}.jpg"]
    assert (tmp_path / f"{BASE}.m4a_original").exists()


def test_overwritten_thumbnail_counts_as_new_output(tmp_path):
    _touch(tmp_path, f"{BASE}.m4a")
    _touch(tmp_path, f"{BASE}.jpg")
    before = snapshot(tmp_path)
    removed = remove_intermediates(tmp_path, BASE, before, overwrite=True)
    assert removed == [f"{BASE}.jpg"]
    assert (tmp_path / f"{BASE}.m4a").exists()


def test_never_touches_other_files(tmp_path):
    other = "수평선 (水平線, back number) ⧸ 하나코 나나 COVER"
    _touch(tmp_path, f"{other}.jpg")
    _touch(tmp_path, f"{other}.m4a_original")
    before = snapshot(tmp_path)
    _touch(tmp_path, f"{BASE}.jpg")
    remove_intermediates(tmp_path, BASE, before, overwrite=False)
    assert (tmp_path / f"{other}.jpg").exists()
    assert (tmp_path / f"{other}.m4a_original").exists()


def test_intermediate_names_exclude_final_audio():
    assert f"{BASE}.m4a" not in intermediate_names(BASE)
