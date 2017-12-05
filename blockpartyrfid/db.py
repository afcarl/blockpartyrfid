#!/usr/bin/env python

import numpy

from . import consts


def sel(vs, board=None, event=None, data0=None, data1=None, timerange=None):
    if isinstance(event, (str, unicode)):
        event = consts.event_strings[event]
    if isinstance(data0, (str, unicode)):
        data0 = consts.data_strings[event][0][data0]
    if isinstance(data1, (str, unicode)):
        data1 = consts.data_strings[event][1][data1]
    m = numpy.ones(vs.shape[0], dtype='bool')
    if board is not None:
        m &= (vs[:, consts.BOARD_COLUMN] == board)
    if event is not None:
        m &= (vs[:, consts.EVENT_COLUMN] == event)
    if data0 is not None:
        m &= (vs[:, consts.DATA0_COLUMN] == data0)
    if data1 is not None:
        m &= (vs[:, consts.DATA1_COLUMN] == data1)
    if timerange is not None:
        assert len(timerange) == 2
        m &= (vs[:, consts.TIME_COLUMN] < timerange[1])
        m &= (vs[:, consts.TIME_COLUMN] > timerange[0])
    return vs[m]


def _reduce_dict(d):
    if isinstance(d, (list, tuple, numpy.ndarray)):
        return d
    if isinstance(d, dict):
        if len(d.keys()) == 1 and d.keys()[0] is None:
            return _reduce_dict(d[None])
        else:
            return {k: _reduce_dict(d[k]) for k in d}
    raise TypeError("Cannot reduce type: %s" % type(d))


def split_events(vs, board=True, event=True, data0=True, data1=True):
    svs = {}
    if board:
        bids = all_boards(vs)
    else:
        bids = [None, ]
    if event:
        evs = numpy.unique(vs[:, consts.EVENT_COLUMN])
    else:
        evs = [None, ]
    for bid in bids:
        svs[bid] = {}
        for ev in evs:
            d = sel(vs, board=bid, event=ev)
            if data0:
                d0s = numpy.unique(d[:, consts.DATA0_COLUMN])
            else:
                d0s = [None, ]
            if data1:
                d1s = numpy.unique(d[:, consts.DATA1_COLUMN])
            else:
                d1s = [None, ]
            svs[bid][ev] = {}
            for d0 in d0s:
                svs[bid][ev][d0] = {}
                for d1 in d1s:
                    svs[bid][ev][d0][d1] = sel(d, data0=d0, data1=d1)
    # re-combine
    return _reduce_dict(svs)


def all_boards(vs):
    return numpy.unique(vs[:, consts.BOARD_COLUMN])


def all_animals(vs):
    return numpy.unique(sel(vs, event='rfid')[:, consts.RFID_ID_COLUMN])


def by_animal(events):
    aids = all_animals(events)
    return {aid: sel(events, event='rfid', data0=aid) for aid in aids}


def find_adjacent(a, b, return_mask=False):
    """for each event in a, find the next, and previous event in b
    return [previous_b_time, next_b_time, previous_b_index, next_b_index]
    None for time/index if no event was found
    """
    a_times = a[:, consts.TIME_COLUMN]
    b_times = b[:, consts.TIME_COLUMN]
    ninds = numpy.searchsorted(b_times, a_times, side='right')
    pmask = ninds == 0
    nmask = ninds == len(b_times)
    ninds[pmask] = 0
    ninds[nmask] = 0
    r = numpy.empty([len(a_times), 4], dtype='f8')
    r[:, 0] = b_times[ninds - 1]
    r[:, 1] = b_times[ninds]
    r[:, 2] = ninds - 1
    r[:, 3] = ninds

    # set invalid times/indices to nan
    r[pmask, 0] = numpy.nan
    r[pmask, 2] = numpy.nan
    r[nmask, 1] = numpy.nan
    r[nmask, 3] = numpy.nan
    if return_mask:
        return r, numpy.logical_and(pmask, nmask)
    return r


def select_events_by_duration(bd, min_t=100, max_t=5000):
    """returns events with
        [time, board, type, bd[:,3], duration]
    """
    # find transitions and calculate durations
    bb = numpy.diff(bd, axis=0)
    # take all falling edges
    bm = bb[:, 4] == -1
    # get start times
    ts = bd[:-1][bm]
    # and durations
    ds = bb[bm][:, 0]
    # find all with duration > min_t
    dm = numpy.logical_and(ds > min_t, ds < max_t)
    # return times and durations
    cts = ts[dm].copy()
    cts[:, 4] = ds[dm]
    return cts


def closest_event(evs, t, max_dt=None):
    dts = numpy.abs(evs[:, consts.TIME_COLUMN] - t)
    i = dts.argmin()
    if max_dt is not None and dts[i] > max_dt:
        return None
    return evs[i]

    
def next_event(evs, t, max_dt=None):
    dts = evs[:, consts.TIME_COLUMN] - t
    dts[dts < 0] = dts.max()
    i = dts.argmin()
    if max_dt is not None and dts[i] > max_dt:
        return None
    return evs[i]


def sum_range(a):
    """ sum ranges [column 0 = start_time, column 1 = end_time]
    without double counting overlaps"""
    s = 0
    if len(a) == 0:
        return s
    for i in range(len(a) - 1):
        if a[i, 1] > a[i + 1, 0]:
            s += a[i + 1, 0] - a[i, 0]
        else:
            s += a[i, 1] - a[i, 0]
    s += a[-1, 1] - a[-1, 0]
    return s


def beam_events_to_duration(be, min_duration=None):
    if len(numpy.unique(be[:, consts.DATA0_COLUMN])) != 1:
        raise Exception("events must be pre-split into left/right")
    while (be[0, consts.DATA1_COLUMN] != 1):
        be = be[1:]
    while (be[-1, consts.DATA1_COLUMN] != 0):
        be = be[:-1]
    d = be[::2].copy()
    d[:, 1] = be[1::2, consts.TIME_COLUMN]
    d[:, 2] = d[:, 1] - d[:, 0]
    if min_duration is not None:
        d = d[d[:, 2] >= min_duration]
    return d[:, :3]


def rfid_events_to_duration(re, min_duration=None):
    while (
            (re[0, consts.DATA1_COLUMN] != 1) or
            (re[0, consts.DATA0_COLUMN] != 1)):
        re = re[1:]
    while (
            (re[-1, consts.DATA1_COLUMN] != 1) or
            (re[-1, consts.DATA0_COLUMN] != 0)):
        re = re[:-1]
    d = re[::3].copy()
    d[:, 1] = re[2::3, consts.TIME_COLUMN]
    d[:, 2] = d[:, 1] - d[:, 0]
    d[:, 3] = re[1::3, consts.DATA0_COLUMN]
    if min_duration is not None:
        d = d[d[:, 2] >= min_duration]
    return d[:, :4]

    
def find_overlapping_durations(a, b, margin=None):
    if margin is None:
        margin = [0, 0]
    inds = []
    for ai in xrange(len(a)):
        sa = a[ai]
        st = sa[0] - margin[0]
        et = sa[1] + margin[1]
        i = numpy.where(
            numpy.logical_not((b[:, 0] > et) | (b[:, 1] < st)))[0]
        #i = numpy.where(
        #    ((b[:, 0] < st) & (b[:, 1] > st)) |
        #    ((b[:, 0] < et) & (b[:, 1] > et)))[0]
        inds.append(list(i))
    return inds

    
def find_neighbors(
        ri, rlo, lro, rio, lio,
        linds=None, rinds=None, iinds=None, visited=None):
    if rinds is None:
        rinds = []
        linds = []
        iinds = []
        visited = set()
     if len(rlo[ri]) != 0:  # has overlapping 'left'
        linds.append(rlo[ri])
        # recurse on lro
        for li in rlo[ri]:
            for sri in lro[li]:
                if sri not in visited:
                    sl, sr, si = find_neighbors(
                        sri, rlo, lro, rio, lio,
                        linds, rinds, iinds, visited)
                    visited.add(sri)
    # for each right index find overlapping
    pass
    
def find_tube_events(board_events, margin=None, min_duration=None):
    if len(numpy.unique(board_events[:, consts.BOARD_COLUMN])) != 1:
        raise Exception("Only works for 1 board")
    # find left/right beam events
    lbe = beam_events_to_duration(
        sel(board_events, event='beam', side='l'), min_duration)
    rbe = beam_events_to_duration(
        sel(board_events, event='beam', side='r'), min_duration)
    ie = rfid_events_to_duration(
        sel(board_events, event='rfid'))
    # find overlapping beam durations
    rlo = find_overlapping_durations(rbe, lbe)
    lro = find_overlapping_durations(lbe, rbe)
    rio = find_overlapping_durations(rbe, ie)
    lio = find_overlapping_durations(lbe, ie)
    # merge beam durations
    tube_events = []
    visited = []
    for ri in xrange(len(rlo)):
        if ri in visited:
            continue
        # for each index in right, find 'neighbors'
        linds, rinds, iinds = find_neighbors(ri, rlo, lro, rio, lio)
        te = {
            'start': st,
            'end': et,
            'lbi': linds,
            'rbi': rinds,
            'ii': iinds,
        }
        tube_events.append(te)
        visited.extend(rinds)