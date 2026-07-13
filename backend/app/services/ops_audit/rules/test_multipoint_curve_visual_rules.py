from app.services.ops_audit.rules.multipoint_curve_visual_rules import (
    build_multipoint_curve_visual_tasks,
)


def _form(**overrides):
    form = {
        "WORKINGORDERCODE": "CH1",
        "POLLUTANTTYPE": "O3",
        "MCLBZ10": "90",
        "MCLBZ20": "160",
        "MCLBZ40": "240",
        "MCLBZ60": "320",
        "MCLBZ80": "410",
    }
    form.update(overrides)
    return form


def _attachment(filename, *, typecode="RF_Q_GaseousMultipoint_O3"):
    return {
        "refid": "CH1",
        "typecode": typecode,
        "filename": filename,
        "filepath": f"/WebFiles/{filename}",
        "file_url": f"http://example.test/{filename}",
    }


def test_build_tasks_uses_valid_form_concentrations(tmp_path):
    tasks = build_multipoint_curve_visual_tasks(
        {"WORKINGORDERCODE": "CH1", "STATIONID": "1001"},
        [
            (
                "RF_Q_GASEOUSMULTIPOINT_O3",
                _form(MCLBZ20="/", MCLBZ40="无", MCLBZ60="invalid"),
            )
        ],
        [],
        [],
        evidence_dir=tmp_path,
    )

    assert len(tasks) == 1
    assert tasks[0]["form_concentrations"] == [90.0, 410.0]
    assert tasks[0]["pollutant"] == "O3"
    assert tasks[0]["unit"] == "ppb"
    assert tasks[0]["evidence_dir"] == str(tmp_path.resolve())


def test_build_tasks_ignores_non_multipoint_forms(tmp_path):
    tasks = build_multipoint_curve_visual_tasks(
        {"WORKINGORDERCODE": "CH1"},
        [("RF_W_GASEOUSCHECK_O3", _form())],
        [],
        [],
        evidence_dir=tmp_path,
    )

    assert tasks == []


def test_build_tasks_selects_curves_and_excludes_point_and_record_photos(tmp_path):
    attachments = [
        _attachment("梯度图.jpg"),
        _attachment("O3多点曲线.png"),
        _attachment("SO2多点记录表.jpg"),
        _attachment("O3多点90.jpg"),
        _attachment("现场照片.jpg"),
    ]

    tasks = build_multipoint_curve_visual_tasks(
        {"WORKINGORDERCODE": "CH1"},
        [("RF_Q_GASEOUSMULTIPOINT_O3", _form())],
        attachments,
        [],
        evidence_dir=tmp_path,
    )

    assert [item["filename"] for item in tasks[0]["candidate_items"]] == [
        "梯度图.jpg",
        "O3多点曲线.png",
    ]
    assert tasks[0]["candidate_items"][0]["original_path"] == "/WebFiles/梯度图.jpg"
