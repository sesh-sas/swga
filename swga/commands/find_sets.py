import functools
import json
import os
import signal
import subprocess
import sys
import time

import click
from pkg_resources import resource_filename

import swga.database
import swga.graph as graph
import swga.locate as locate
import swga.score as score
from swga.clint.textui import progress
from swga.commands import Command
from swga.database import Primer, Set, update_in_chunks, init_db


graph_fname = "compatibility_graph.dimacs"

def main(argv, cfg_file):
    cmd = Command('find_sets', cfg_file=cfg_file)
    cmd.parse_args(argv)
    init_db(cmd.primer_db)

    # We need to clear all the previously-used sets each time due to uniqueness
    # constraints
    allsets = Set.select()
    if allsets.count() > 0:
        click.confirm("Remove all previously-found sets?", abort=True)
        for s in progress.bar(allsets, expected_size=allsets.count()):
            s.primers.clear()
            s.delete_instance()

    make_graph(cmd.max_hetdimer_bind, graph_fname)

    setlines = find_sets(
        cmd.min_bg_bind_dist,
        cmd.min_size,
        cmd.max_size,
        cmd.bg_genome_len)
    
    score_sets(
        setlines,
        cmd.fg_genome_fp,
        cmd.score_expression,
        cmd.max_fg_bind_dist,
        cmd.max_sets,
        cmd.plugin_score_fun)
    
    
def make_graph(max_hetdimer_bind, outfile):
    '''Selects all active primers and outputs a primer compatibility graph.'''

    # Reset all the primer IDs (as ids are only used for set_finder)
    Primer.update(_id = -1).execute()

    primers = list(Primer.select().where(Primer.active==True)
                   .order_by(Primer.ratio.desc()).execute())
    
    if len(primers) == 0:
       swga.swga_error("No active sets found. Run `swga filter` first.")

    for i, p in enumerate(primers):
        p._id = i + 1

    update_in_chunks(primers, show_progress=False)

    swga.message("Composing primer compatibility graph...")
    edges = graph.test_pairs(primers, max_hetdimer_bind)

    if len(edges) == 0:
        swga.swga_error("No compatible primers. Try relaxing your parameters.")

    with open(outfile, 'wb') as out:
        graph.write_graph(primers, edges, out)

        
def find_sets(
        min_bg_bind_dist,
        min_size,
        max_size,
        bg_genome_len,
        graph_fname=graph_fname):
    swga.message("Now finding sets. If nothing appears, try relaxing your parameters.")
    set_finder = resource_filename("swga", "bin/set_finder")
    find_set_cmd = [set_finder, '-q', '-q', '-B', min_bg_bind_dist,
                    '-L', bg_genome_len, '-m', min_size, '-M',
                    max_size, '-a', '-u', '-r', 'unweighted-coloring',
                    graph_fname]
    find_set_cmd = " ".join([str(_) for _ in find_set_cmd])

    # We call the set_finder command as a line-buffered subprocess that passes
    # its output back to this process. The function then yields each line as a
    # generator; when close() is called, it terminates the set_finder subprocess.
    process = subprocess.Popen(find_set_cmd, shell=True, stdout=subprocess.PIPE,
                               preexec_fn=os.setsid, bufsize=1)
    try:
        for line in iter(process.stdout.readline, b''):
            (yield line)
    finally:
        time.sleep(0.1)
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)

        
def score_sets(
        setlines, 
        fg_genome_fp,
        score_expression,
        max_fg_bind_dist,
        max_sets,
        plugin_score_fun=None):
    '''
    Retrieves the primers and their binding locations from the output of
    find_sets and calculates the max binding distance between primers in the
    foreground genome.

    If the max distance is below a specified threshold, it passes the set
    and some additional attributes to a user-defined score function.

    After a specified number of sets pass the filter, it exits the process.
    '''

    if max_sets < 1:
        max_sets = float("inf")

    # Find the user-defined scoring function    
    score_fun = None
    if score_expression and plugin_score_fun:
        swga.warn("Warning: User or config file specified both scoring"
                  " expression and plugin score function. Using the plugin score"
                  " function given by %s." % plugin_score_fun)
        score_fun = swga.get_user_fun(score_fun)
    elif score_expression:
        score_fun = functools.partial(
            score.default_score_set,
            expression=score_expression)

    chr_ends = locate.chromosome_ends(fg_genome_fp)

    passed = processed = 0
    min_max_dist = float('inf')
    
    status = "\rSets: {: ^5,.6g} | Passed: {: ^5,.6g} | Smallest max binding distance:{: ^12,.4G}"


    try:
        for line in setlines:
            try:
                primer_ids, bg_ratio = score.read_set_finder_line(line)
            except ValueError:
                swga.warn("Could not parse line:\n\t"+line)
                continue
            primers = swga.database.get_primers_for_ids(primer_ids)
            processed += 1
            
            # Add chromosome ends to locations to make distances accurate
            binding_locations = locate.linearize_binding_sites(primers, chr_ends)
            max_dist = max(score.seq_diff(binding_locations))

            # Remember the smallest max distance seen so far
            min_max_dist = min_max_dist if max_dist > min_max_dist else max_dist

            # Score the set if it passes the binding cutoff
            if max_dist <= max_fg_bind_dist:
                passed += 1
                
                set_score, variables = score_fun(
                    primer_set=primers,
                    primer_locs=binding_locations,
                    max_dist=max_dist,
                    bg_ratio=bg_ratio,
                    output_handle=sys.stdout)

                swga.database.add_set(
                    _id = passed,
                    primers=primers, 
                    score=set_score, 
                    scoring_fn=score_expression,
                    **variables)
            
            swga.message(
                status.format(processed, passed, min_max_dist), newline=False)
            if passed >= max_sets:
                swga.message("\nDone (scored %i sets)" % passed)
                break
    finally:
        # Raises a GeneratorExit inside the find_sets command, prompting it to quit
        # the subprocess
        setlines.close()
    
