"""Burnable-wildland mask from GLDAS classes and regridding onto ERA5 nodes."""

import numpy as np

from earthburns.mask import (
    BURNABLE_CLASSES_DEFAULT,
    burnable_from_classes,
    nearest_nw_regrid_to_nodes,
    vote_regrid_to_nodes,
)


def test_burnable_from_classes_default_set():
    classes = np.array([[0, 1, 5, 10], [12, 13, 16, 18]], dtype=np.int16)
    out = burnable_from_classes(classes, BURNABLE_CLASSES_DEFAULT)
    assert out.tolist() == [[False, True, True, True], [False, False, False, True]]


def test_burnable_from_classes_custom_set():
    classes = np.array([1, 2, 3])
    assert burnable_from_classes(classes, frozenset({2})).tolist() == [False, True, False]


def _two_by_two():
    # source cell centres (GLDAS-like, half-cell offset), descending lat like the canonical grid
    return np.array([0.375, 0.125]), np.array([0.125, 0.375])


def test_vote_regrid_majority_of_four_neighbours():
    src_lat, src_lon = _two_by_two()
    tgt_lat, tgt_lon = np.array([0.25]), np.array([0.25])

    def run(cells):
        src = np.array(cells, dtype=bool)
        return vote_regrid_to_nodes(src, src_lat, src_lon, tgt_lat, tgt_lon)[0, 0]

    assert run([[1, 1], [1, 1]])
    assert run([[1, 1], [0, 0]])  # 2 of 4 -> burnable (fraction >= 0.5)
    assert not run([[1, 0], [0, 0]])  # 1 of 4
    assert not run([[0, 0], [0, 0]])


def test_vote_regrid_outside_source_extent_is_false():
    src_lat, src_lon = _two_by_two()
    tgt_lat, tgt_lon = np.array([0.25, -60.0]), np.array([0.25])
    out = vote_regrid_to_nodes(np.ones((2, 2), bool), src_lat, src_lon, tgt_lat, tgt_lon)
    assert out.shape == (2, 1)
    assert out[0, 0] and not out[1, 0]


def test_vote_regrid_wraps_longitude_at_dateline():
    src_lat = np.array([0.375, 0.125])
    src_lon = np.array([-179.875, 179.875])  # the two cells adjacent to lon = -180 / 180
    src = np.array([[True, True], [True, True]])
    out = vote_regrid_to_nodes(src, src_lat, src_lon, np.array([0.25]), np.array([-180.0]))
    assert out[0, 0]


def test_nearest_nw_regrid_picks_north_west_cell():
    src_lat, src_lon = _two_by_two()
    src = np.array([[7, 8], [9, 10]], dtype=np.int16)
    out = nearest_nw_regrid_to_nodes(src, src_lat, src_lon, np.array([0.25]), np.array([0.25]))
    assert out[0, 0] == 7


def test_nearest_nw_regrid_outside_extent_is_fill():
    src_lat, src_lon = _two_by_two()
    src = np.array([[7, 8], [9, 10]], dtype=np.int16)
    out = nearest_nw_regrid_to_nodes(
        src, src_lat, src_lon, np.array([-80.0]), np.array([0.25]), fill=0
    )
    assert out[0, 0] == 0
