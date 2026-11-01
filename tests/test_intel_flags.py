from core.intel import flags


def test_default_off_and_file_and_env(tmp_path, monkeypatch):
    monkeypatch.setattr(flags, "PATH", tmp_path / "f.json")
    monkeypatch.delenv("INTEL_ALIGN", raising=False)
    assert flags.flag("ALIGN") is False
    flags.set_flag("ALIGN", True, "tester", "n")
    assert flags.flag("align") is True
    d = flags.all_flags()["ALIGN"]
    assert d["on"] is True and d["by"] == "tester" and d["note"] == "n" and d["at"] > 0
    monkeypatch.setenv("INTEL_ALIGN", "off")
    assert flags.flag("ALIGN") is False
    monkeypatch.setenv("INTEL_ALIGN", "on")
    flags.set_flag("ALIGN", False, "t", "")
    assert flags.flag("ALIGN") is True
    assert not list(tmp_path.glob("*.tmp"))


def test_corrupt_file_is_off(tmp_path, monkeypatch):
    p = tmp_path / "f.json"
    p.write_text("{bad")
    monkeypatch.setattr(flags, "PATH", p)
    monkeypatch.delenv("INTEL_ALIGN", raising=False)
    assert flags.flag("ALIGN") is False and flags.all_flags() == {}
