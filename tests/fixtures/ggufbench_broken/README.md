# ggufbench malformed artifact fixtures — deliberately outside ../ggufbench/ so
# whole-root queries over the clean tree never trip over them.
#
# Score-boundary rows live here too (nonfinite-score-*, huge-int-score):
# ggufbench_store._map_row must refuse any score outside the finite float domain
# instead of letting NaN/Infinity hijack a proposal ranking or OverflowError
# escape as an unstructured crash.
