# -*- coding: utf-8 -*-
import colour
import glob
from collections import defaultdict
import re
from language import read_answers_file
import itertools
import random


def get_roc_trail(answers, truth):
    rmap = {}
    for k, v in answers.items():
        t = truth[k]
        r = rmap.setdefault(v, [0, 0])
        r[0] += t
        r[1] += not t
    return [(score, d[0], d[1])
            for score, d in sorted(rmap.items())]


def calc_roc_from_trail(roc_trail, n_true, n_false):
    true_positives, false_positives = n_true, n_false
    tp_scale = 1.0 / (n_true or 1)
    fp_scale = 1.0 / (n_false or 1)
    px, py = 1, 1  # previous position for area calculation
    auc = 1.0

    for score, positives, negatives in roc_trail:
        false_positives -= negatives
        true_positives -= positives
        x = false_positives * fp_scale
        y = true_positives * tp_scale
        auc += (px + x) * 0.5 * (y - py)
        px = x
        py = y

    auc += px * 0.5 * -py  # is this ever necesssary?
    return auc


def calc_auc(answers, truth):
    results = get_roc_trail(answers, truth)
    n_true = sum(truth.values())
    n_false = len(truth) - n_true
    return calc_roc_from_trail(results, n_true, n_false)


def calc_cat1(answers, truth):
    # (1/n)*(nc+(nu*nc/n))
    n_correct = 0
    n_undecided = 0
    n = len(answers)
    for k, v in answers.items():
        if v == 0.5:
            n_undecided += 1
        else:
            n_correct += (v > 0.5) == truth[k]

    scale = 1.0 / n
    return (n_correct + n_undecided * n_correct * scale) * scale


def print_candidate(b, c='', prefix='best', fn=''):
    if fn:
        fn = "%20s" % fn
    print ("%s%9s %s auc*cat1 %.4f; cat1 %.3f; auc %.3f; range (%d-%d) "
           "(%.3f - %.3f) undecided %2d; correct %2d tp %2d tf %2d" %
           ((c, prefix, fn) + b) + colour.C_NORMAL)


def split_roc_trail(orig_trail, s, e):
    head = orig_trail[:s]
    middle = orig_trail[s:e]
    target = orig_trail[e]
    score_e = target[0]
    if middle:
        score_s = middle[0][0]
    else:
        score_s = score_e

    tail = orig_trail[e + 1:]
    score, positives, negatives = target
    for _, p, n in middle:
        positives += p
        negatives += n
    return head, [(score, positives, negatives)], tail, score_s, score_e


def search(answers, truth, verbose=False):
    roc_trail = get_roc_trail(answers, truth)
    n_true = sum(truth.values())
    n_false = len(truth) - n_true

    index_keys = (0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75)
    indices = {k: 0 for k in index_keys}
    for i, x in enumerate(roc_trail):
        score, u_pos, u_neg = x
        for k, v in indices.items():
            if score <= k:
                indices[k] = i

    if verbose:
        print "searching around"
        print indices
    rindices = {v: k for k, v in indices.items()}

    auc = calc_roc_from_trail(roc_trail, n_true, n_false)
    default_cat1 = calc_cat1(answers, truth)
    default_score = auc * default_cat1

    # at bottom end of scale
    true_positives = n_true
    true_negatives = 0
    scale = 1.0 / len(truth)
    candidates = []
    best_candidate = (0,)
    indicators = {}

    if verbose:
        print_c = print_candidate
    else:
        def print_c(*args, **kwargs):
            pass

    for i, roc_data in enumerate(roc_trail):
        score, positives, negatives = roc_data
        true_positives -= positives
        n_undecided = positives + negatives
        n_correct = true_positives + true_negatives
        cat1 = (n_correct + n_undecided * n_correct * scale) * scale
        candidate = (cat1 * auc, cat1, auc, i, i, score, score,
                     n_undecided, n_correct, true_positives, true_negatives)
        if candidate > best_candidate:
            best_candidate = candidate
        true_negatives += negatives

    print_c(best_candidate)
    indicators['centre'] = best_candidate
    centre = best_candidate[3]

    min_s = min(max(centre - 20, 0), indices[0.45])
    max_s = max(min(centre + 20, len(roc_trail)), indices[0.75])
    for s in range(min_s, max_s):
        for e in range(s, max_s):
            head, middle, tail, score_s, score_e = split_roc_trail(roc_trail,
                                                                   s, e)
            auc = calc_roc_from_trail(head + middle + tail, n_true, n_false)
            score, u_pos, u_neg = middle[0]
            n_undecided = u_pos + u_neg
            n_tp = sum(x[1] for x in tail)
            n_tf = sum(x[2] for x in head)
            n_correct = n_tp + n_tf
            cat1 = (n_correct + n_undecided * n_correct * scale) * scale
            candidate = (cat1 * auc, cat1, auc, s, e, score_s, score_e,
                         n_undecided, n_correct, n_tp, n_tf)
            candidates.append(candidate)
            if candidate > best_candidate:
                best_candidate = candidate
                print_c(candidate)
                indicators['range'] = candidate
            if s in rindices and e in rindices:
                if candidate > indicators['centre']:
                    c = colour.GREEN
                elif candidate[0] > default_score:
                    c = colour.YELLOW
                else:
                    c = colour.RED
                if s != e:
                    name = '%d-%d' % (rindices[s] * 100, rindices[e] * 100)
                else:
                    name = '%d' % (rindices[s] * 100,)
                print_c(candidate, c, prefix=name)
                indicators[name] = candidate

    return indicators


def get_shortname(fn, epoch_from_filename=False):
    m = re.search(r'answers-([^/]+)/[^\d]+(\d+)?', fn)
    if m:
        shortname = m.group(1)
        if epoch_from_filename:
            shortname = '%s-%s' % (shortname, m.group(2))
    else:
        shortname = fn
    return shortname


def _get_results(file_pattern, truth, epoch_from_filename=False,
                 use_shortname=True):
    results = defaultdict(list)
    for fn in glob.glob(file_pattern):
        answers = read_answers_file(fn)
        indicators = search(answers, truth)
        if use_shortname:
            fn = get_shortname(fn, epoch_from_filename)
        for k, v in indicators.items():
            results[k].append((v, fn))
    return results


def _find_winners(results):
    winners = []
    for k, v in sorted(results.items()):
        v.sort()
        v.reverse()
        winners.append((v[0][0], v[0][1], k))
    return winners


def _get_sorted_scores(results):
    totals = {}
    for x in results.values():
        for candidate, fn in x:
            t = totals.setdefault(fn, [0.0, 0])
            t[0] += candidate[0]
            t[1] += 1

    top_scores = sorted((v[0] / v[1], k) for k, v in totals.items())
    top_scores.reverse()
    return top_scores


def search_answer_files(file_pattern, truth, epoch_from_filename=False):
    results = _get_results(file_pattern, truth, epoch_from_filename)

    winners = _find_winners(results)
    best = max(c[0] for c, n, k in winners if not k.isalpha())
    near = best * 0.99
    for candidate, name, key in winners:
        if key.isalpha():
            c = colour.CYAN
        elif candidate[0] == best:
            c = colour.YELLOW
        elif candidate[0] > near:
            c = colour.MAGENTA
        else:
            c = ''
        print_candidate(candidate, c, prefix=key, fn=name)

    top_scores = _get_sorted_scores(results)

    colour_map = {t[1]: c for c, t
                  in zip(colour.spectra['warm'], top_scores)}

    for score, name in top_scores:
        print "%s%s %.3f%s" % (colour_map.get(name, ''), name, score,
                               colour.C_NORMAL),
    print
    notable_commits = set(x[1] for x in top_scores[:5])
    for k, v in sorted(results.items()):
        print "%8s" % k,
        notable_commits.add(v[0][1])
        for candidate, fn in v[:10]:
            print "%s%s %.3f%s" % (colour_map.get(fn, ''), fn, candidate[0],
                                   colour.C_NORMAL),
        print

    for name in notable_commits:
        print "%s%s%s" % (colour_map.get(name, ''), name,
                          colour.C_NORMAL),
    print


def search_commits(file_pattern, truth, n=8, epoch_from_filename=False):
    results = _get_results(file_pattern, truth, epoch_from_filename)
    top_scores = _get_sorted_scores(results)
    notable_commits = set(x[1] for x in top_scores[:n])
    for v in results.values():
        notable_commits.add(v[0][1])
    for name in notable_commits:
        print name


def search_one(answers, truth, verbose=False):
    indicators = search(answers, truth, verbose=verbose)
    best = max(v[0] for k, v in indicators.items() if not k.isalpha())
    near = best * 0.99
    for k, v in sorted(indicators.items()):
        if k.isalpha():
            c = colour.CYAN
        elif v[0] == best:
            c = colour.YELLOW
        elif v[0] > near:
            c = colour.MAGENTA
        else:
            c = ''
        print_candidate(v, c, prefix=k)
    return indicators


def test_ensembles(file_pattern, ensemble_size, truth,
                   cutoff=10, replace=False, randomise=False,
                   epoch_from_filename=False):

    results = _get_results(file_pattern, truth, epoch_from_filename,
                           use_shortname=False)
    top_scores = _get_sorted_scores(results)
    if randomise:
        random.shuffle(top_scores)

    singles = {}
    for _, fn in sorted(top_scores[:cutoff]):
        shortname = get_shortname(fn)
        singles[shortname] = read_answers_file(fn)
        print "%s %.3f" % (shortname, _)

    ensembles = []
    if replace:
        combos = itertools.combinations_with_replacement
    else:
        combos = itertools.combinations

    for names in combos(singles.keys(), ensemble_size):
        ensemble = {}
        for n in names:
            answers = singles.get(n)
            for k, v in answers.items():
                score = ensemble.get(k, 0.0)
                ensemble[k] = score + v

        indicators = search(ensemble, truth)
        ensembles.append((indicators['centre'], names, indicators))

    ensembles.sort()
    centre_sum = 0.0
    centre_sum2 = 0.0

    for i, x in enumerate(ensembles):
        c, names, indicators = x
        name = '-'.join(names)
        n = len(set(names))
        if n == 1:
            _colour = colour.RED
        elif n < ensemble_size:
            _colour = colour.YELLOW
        else:
            _colour = colour.C_NORMAL
        if i == len(ensembles) // 2:
            _colour = colour.MAGENTA
        centre = c[5] / ensemble_size
        centre_sum += centre
        centre_sum2 += centre * centre

        print "%s%s%s %.3f auc %.3f c@1 %.3f centre %.2f" % (_colour,
                                                             name,
                                                             colour.C_NORMAL,
                                                             c[0], c[2], c[1],
                                                             centre)

    centre_mean = centre_sum / len(ensembles)
    centre_dev = (centre_sum2 / len(ensembles) -
                  centre_mean * centre_mean) ** 0.5
    print "%scentre %.3f±%.3f%s" % (colour.YELLOW, centre_mean, centre_dev,
                                    colour.C_NORMAL)
