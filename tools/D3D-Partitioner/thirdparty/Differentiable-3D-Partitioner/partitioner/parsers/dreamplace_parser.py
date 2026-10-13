'''
Author: JeanneWillis hi@jeannewillis.cn
Date: 2026-02-05 16:56:01
LastEditors: JeanneWillis hi@jeannewillis.cn
LastEditTime: 2026-02-11 04:53:55
FilePath: /Differentiable-3D-Partitioner/partitioner/parsers/dreamplace_parser.py
Description: using DREAMPlace to parse the design
'''
import json
import os
import random
import sys

import numpy as np
import torch

_project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_dreamplace_install_dir = os.path.join(_project_root, 'thirdparty',
                                       'DREAMPlace', 'install')
_dreamplace_source_dir = os.path.join(_dreamplace_install_dir, 'dreamplace')

if "dreamplace" not in sys.modules:
    if os.path.exists(_dreamplace_install_dir):
        if _dreamplace_install_dir not in sys.path:
            sys.path.insert(0, _dreamplace_install_dir)

    if _dreamplace_source_dir not in sys.path:
        sys.path.insert(0, _dreamplace_source_dir)

import dreamplace.PlaceDB as PlaceDB
import dreamplace.Params as Params
import dreamplace.NonLinearPlace as NonLinearPlace
import dreamplace.PlaceObj as PlaceObj


class DreamplaceParser:

    def __init__(self):
        self.num_nodes = 0
        self.num_nets = 0
        self.num_pins = 0

        self.node_pos = None
        self.pin_pos = None
        self.flat_net2pin_map = None
        self.flat_net2pin_start_map = None
        self.pin2node_map = None

        self.node_size_x = None
        self.node_size_y = None

        self.die_xl = None
        self.die_yl = None
        self.die_xh = None
        self.die_yh = None
        self._density_place_obj = None

    def _initialize_density_ops(self, params, placedb, basic_place):
        if getattr(basic_place.op_collections, "density_op", None) is not None:
            return

        global_place_stages = getattr(params, "global_place_stages", None)
        if not global_place_stages:
            raise RuntimeError(
                "DREAMPlace density_op is required by the differentiable "
                "partitioner, but global_place_stages is empty.")
        global_place_params = global_place_stages[0]
        density_place_obj = PlaceObj.PlaceObj(
            0.0,
            params,
            placedb,
            basic_place.data_collections,
            basic_place.op_collections,
            global_place_params,
        ).to(basic_place.data_collections.pos[0].device)
        if getattr(basic_place.op_collections, "density_op", None) is None:
            raise RuntimeError(
                "Failed to initialize DREAMPlace density_op for the "
                "differentiable partitioner.")
        self._density_place_obj = density_place_obj

    def parse_design(self, dreamplace_config_file):
        with open(dreamplace_config_file, 'r', encoding='utf-8') as f:
            dreamplace_config = json.load(f)

        random_seed = dreamplace_config.get('random_seed')
        if random_seed is not None:
            seed = int(random_seed)
            random.seed(seed)
            np.random.seed(seed)
            torch.manual_seed(seed)

        params = Params.Params()
        params.load(dreamplace_config_file)

        placedb = PlaceDB.PlaceDB()
        placedb(params)
        basic_place = NonLinearPlace.NonLinearPlace(params,
                                                    placedb,
                                                    timer=None)
        self._initialize_density_ops(params, placedb, basic_place)

        self.num_nodes = placedb.num_physical_nodes
        self.num_nets = placedb.num_nets
        self.num_pins = placedb.num_pins

        self.node_pos = basic_place.pos[0]
        self.pin_pos = basic_place.op_collections.pin_pos_op(self.node_pos)
        self.flat_net2pin_map = basic_place.data_collections.flat_net2pin_map
        self.flat_net2pin_start_map = basic_place.data_collections.flat_net2pin_start_map
        self.pin2node_map = basic_place.data_collections.pin2node_map
        self.node_size_x = basic_place.data_collections.node_size_x
        self.node_size_y = basic_place.data_collections.node_size_y

        self.die_xl = placedb.xl
        self.die_yl = placedb.yl
        self.die_xh = placedb.xh
        self.die_yh = placedb.yh

        self.placedb = placedb
        self.dreamplace_basic = basic_place

    def attach_existing_design(self, dreamplace, params=None):
        """Expose an already constructed D2D DREAMPlace database.

        ``dreamplace`` is the lightweight D2D ``DreamplaceBase`` wrapper.  It
        already owns the PlaceDB, BasicPlace operators, and current position,
        so reparsing the same LEF/DEF would duplicate the largest resident
        data structures.
        """
        placedb = getattr(dreamplace, 'placedb', None)
        basic_place = getattr(dreamplace, 'basic_place', None)
        if placedb is None or basic_place is None:
            raise ValueError("existing DREAMPlace object is not initialized")

        node_pos = getattr(dreamplace, 'pos', None)
        if node_pos is None:
            basic_pos = getattr(basic_place, 'pos', None)
            if basic_pos is not None and len(basic_pos) > 0:
                node_pos = basic_pos[0]
        if node_pos is None:
            data_pos = getattr(basic_place.data_collections, 'pos', None)
            if data_pos is not None and len(data_pos) > 0:
                node_pos = data_pos[0]
        if node_pos is None:
            raise ValueError("existing DREAMPlace object has no position tensor")

        if getattr(basic_place.op_collections, 'density_op', None) is None:
            if params is None:
                raise ValueError(
                    "params are required to initialize the density operator")
            self._initialize_density_ops(params, placedb, basic_place)

        self.num_nodes = placedb.num_physical_nodes
        self.num_nets = placedb.num_nets
        self.num_pins = placedb.num_pins
        self.node_pos = node_pos
        self.pin_pos = basic_place.op_collections.pin_pos_op(node_pos)
        self.flat_net2pin_map = (
            basic_place.data_collections.flat_net2pin_map)
        self.flat_net2pin_start_map = (
            basic_place.data_collections.flat_net2pin_start_map)
        self.pin2node_map = basic_place.data_collections.pin2node_map
        self.node_size_x = basic_place.data_collections.node_size_x
        self.node_size_y = basic_place.data_collections.node_size_y
        self.die_xl = placedb.xl
        self.die_yl = placedb.yl
        self.die_xh = placedb.xh
        self.die_yh = placedb.yh
        self.placedb = placedb
        self.dreamplace_basic = basic_place
        return self

if __name__ == "__main__":
    parser = DreamplaceParser()
    parser.parse_design(
        "benchmarks/bookself/iccad2022/case2_hidden/dreamplace.json")
