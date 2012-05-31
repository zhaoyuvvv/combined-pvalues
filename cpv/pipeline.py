import sys
import os.path as op

def main():
    return _pipeline()

def _pipeline():
    sys.path.insert(0, op.join(op.dirname(__file__), ".."))
    from cpv import acf, slk, fdr, peaks, region_p, stepsize
    from _common import get_col_num
    import argparse
    import operator

    p = argparse.ArgumentParser(description=__doc__,
                   formatter_class=argparse.RawDescriptionHelpFormatter)

    p.add_argument("-c", dest="c", help="column number that has the value to"
                   "take the  acf", type=int, default=4)
    p.add_argument("--dist", dest="dist", help="Maximum dist to extend the"
             " ACF calculation", type=int)
    p.add_argument("--step", dest="step", help="step size for bins in the"
             " ACF calculation", type=int)
    p.add_argument("--seed", dest="seed", help="A value must be at least this"
                 " large/small in order to seed a region.", type=float,
                 default=0.1)
    p.add_argument("--threshold", dest="threshold", help="After seeding, a value"
                 " of at least this number can extend a region. ",
                 type=float)
    p.add_argument("-p", "--prefix", dest="prefix",
            help="prefix for output files", default=None)

    p.add_argument("-s", dest="stringent", action="store_true", default=False,
            help="use this flag if there is an abundance of low-pvalues.")

    p.add_argument('bed_files', nargs='+', help='sorted bed file to process')

    args = p.parse_args()


    if not (args.prefix):
        sys.exit(p.print_help())

    if not args.threshold:
        args.threshold = args.seed
    assert op.exists(args.bed_files[0])

    col_num = get_col_num(args.c)
    if args.step is None:
        step = stepsize.stepsize(args.bed_files, col_num)
        print >>sys.stderr, "calculated stepsize as: %i" % step
    else:
        step = args.step

    lags = range(1, args.dist, step)
    lags.append(lags[-1] + step)

    # go out to max requested distance but stop once an autocorrelation 
    # < 0.05 is added.
    
    putative_acf_vals = acf.acf(args.bed_files, lags, col_num, simple=False)
    acf_vals = []
    for a in putative_acf_vals:
        # a is ((lmin, lmax), (corr, N))
        # this heuristic seems to work. stop just above the 0.08 correlation
        # lag.
        if a[1][0] < 0.08 and len(acf_vals) > 2: break
        acf_vals.append(a)
        if a[1][0] < 0.08 and len(acf_vals): break

    # save the arguments that this was called with.
    with open(args.prefix + ".args.txt", "w") as fh:
        print >>fh, " ".join(sys.argv[1:]) + "\n"
        import datetime
        print >>fh, "date: %s" % datetime.datetime.today()

    with open(args.prefix + ".acf.txt", "w") as fh:
        acf_vals = acf.write_acf(acf_vals, fh)
        print >>sys.stderr, "wrote: %s" % fh.name
    print >>sys.stderr, "ACF:\n", open(args.prefix + ".acf.txt").read()
    with open(args.prefix + ".slk.bed", "w") as fh:
        for row in slk.adjust_pvals(args.bed_files, col_num, acf_vals, 
                args.stringent):
            fh.write("%s\t%i\t%i\t%.4g\t%.4g\n" % row)
        print >>sys.stderr, "wrote: %s" % fh.name

    with open(args.prefix + ".fdr.bed", "w") as fh:
        for bh, l in fdr.fdr(args.prefix + ".slk.bed", -1):
            fh.write("%s\t%.4g\n" % (l.rstrip("\r\n"), bh))
        print >>sys.stderr, "wrote: %s" % fh.name

    fregions = args.prefix + ".regions.bed"
    with open(fregions, "w") as fh:
        peaks.peaks(args.prefix + ".fdr.bed", -1, args.threshold, args.seed,
            step, fh, operator.le)
    n_regions = sum(1 for _ in open(fregions))
    print >>sys.stderr, "wrote: %s (%i regions)" % (fregions, n_regions)

    with open(args.prefix + ".regions-p.bed", "w") as fh:
        N = 0
        fh.write("#chrom\tstart\tend\tmin_p\tn_probes\tslk_p\tslk_sidak_p\n")
        # use -2 for original, uncorrected p-values in slk.bed
        for region_line, slk_p, slk_sidak_p, sim_p in region_p.region_p(
                               args.prefix + ".slk.bed",
                               args.prefix + ".regions.bed", -2,
                               0, step):
            if sim_p != "NA":
                sim_p = "%.4g" % sim_p
            #fh.write("%s\t%.4g\t%.4g\t%s\n" % (region_line, slk_p, slk_sidak_p, \
            fh.write("%s\t%.4g\t%.4g\n" % (region_line, slk_p, slk_sidak_p))
            #                                     sim_p))
            fh.flush()
            N += int(slk_sidak_p < 0.05)
        print >>sys.stderr, "wrote: %s, (regions with corrected-p < 0.05: %i)" \
                % (fh.name, N)