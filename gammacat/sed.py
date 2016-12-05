# Licensed under a 3-clause BSD style license - see LICENSE.rst
import logging
from astropy.table import Table
from .info import gammacat_info
from .utils import check_ecsv_column_header

__all__ = ['SED', 'SEDList']

log = logging.getLogger(__name__)


class SED:
    """
    Spectral energy distribution (SED)

    Represents on SED.
    """
    expected_colnames = [
        'e_ref', 'e_min', 'e_max',
        'dnde', 'dnde_err', 'dnde_errn', 'dnde_errp', 'dnde_ul',
        'excess', 'significance',
    ]

    expected_colnames_input = expected_colnames + [
        'e_lo', 'e_hi',
        'dnde_min', 'dnde_max',
        'eflux', 'eflux_err',
    ]

    required_meta_keys = [
        'data_type', 'paper_id', 'source_id',
    ]

    allowed_meta_keys = required_meta_keys + [
        'source_name', 'comments', 'url', 'UL_CONF',
    ]

    def __init__(self, table, path):
        self.table = table
        self.path = path

    @classmethod
    def read(cls, path, format='ascii.ecsv'):
        log.debug('Reading {}'.format(path))
        table = Table.read(str(path), format=format)
        return cls(table=table, path=path)

    def process(self):
        """Apply fixes."""
        table = self.table
        self.validate_input()
        self._process_energy_ranges(table)
        self._process_flux_errrors(table)

        self._add_defaults(table)
        self._process_eflux_inputs(table)
        self._process_column_order(table)
        # TODO: add validate_output?

    @staticmethod
    def _process_energy_ranges(table):
        """
        Sometimes energy bin ranges are given as `(e_lo, e_hi)`,
        Those columns are not standard in the SED spec.
        We convert those to `(e_min, e_max)`
        """
        if 'e_lo' in table.colnames:
            table['e_min'] = table['e_ref'] - table['e_lo']
            del table['e_lo']
        if 'e_hi' in table.colnames:
            table['e_max'] = table['e_ref'] + table['e_hi']
            del table['e_hi']

    @staticmethod
    def _process_flux_errrors(table):
        """
        Sometimes flux errors are given as `(dnde_min, dnde_max)`,
        i.e. 68% confidence level (1 sigma) limits.
        Those columns are not standard in the SED spec.
        We convert those to `dnde_errn` and `dnde_errp`.
        """
        if 'dnde_min' in table.colnames:
            table['dnde_errn'] = table['dnde'] - table['dnde_min']
            del table['dnde_min']
        if 'dnde_max' in table.colnames:
            table['dnde_errp'] = table['dnde_max'] - table['dnde']
            del table['dnde_max']

    @staticmethod
    def _add_defaults(table):
        """
        Add default units and description.
        """
        for colname in table.colnames:
            if colname.startswith('e_') and not table[colname].unit:
                table[colname].unit = 'TeV'

            if 'dnde' in colname and not table[colname].unit:
                table[colname].unit = 'cm^-2 s^-1 TeV^-1'

    @staticmethod
    def _process_eflux_inputs(table):
        """
        If `eflux` is given instead of `dnde`
        -> convert to `dnde` to have uniform standard.
        """
        if 'eflux' in table.colnames and 'dnde' not in table.colnames:
            dnde = table['eflux'].quantity / table['e_ref'].quantity ** 2
            table['dnde'] = dnde.to('cm^-2 s^-1 TeV^-1')
            del table['eflux']

    def _process_column_order(self, table):
        """
        Establish a standard column order.
        """
        # See "Select or reorder columns" section at
        # http://astropy.readthedocs.io/en/latest/table/modify_table.html
        colnames = [_ for _ in self.expected_colnames if _ in table.colnames]
        self.table = table[colnames]

    def validate_input(self):
        log.debug('Validating {}'.format(self.path))
        check_ecsv_column_header(self.path)
        self._validate_input_colnames()
        self._validate_input_meta()

    def _validate_input_colnames(self):
        table = self.table
        unexpected_colnames = sorted(set(table.colnames) - set(self.expected_colnames_input))
        if unexpected_colnames:
            log.error(
                'SED file {} contains invalid columns: {}'
                ''.format(self.path, unexpected_colnames)
            )

    def _validate_input_meta(self):
        meta = self.table.meta

        missing = sorted(set(self.required_meta_keys) - set(meta.keys()))
        if missing:
            log.error('SED file {} contains missing meta keys: {}'.format(self.path, missing))

        extra = sorted(set(meta.keys()) - set(self.allowed_meta_keys))
        if extra:
            log.error('SED file {} contains extra meta keys: {}'.format(self.path, extra))

        if ('comments' in meta) and not isinstance(meta['comments'], str):
            log.error('SED file {} contains invalid meta key comments (should be str): {}'
                      ''.format(self.path, meta['comments']))

        if 'UL_CONF' in meta and not (0 < meta['UL_CONF'] < 1):
            log.error('SED file {} contains invalid meta "UL_CONF" value: {}'.format(self.path, meta['UL_CONF']))


class SEDList:
    """
    List of `SED` objects.

    Used to represent the SED data in the input folder.
    """

    def __init__(self, data):
        self.data = data
        _source_ids = [sed.table.meta['source_id'] for sed in data]
        self._sed_by_source_id = dict(zip(_source_ids, data))

    @classmethod
    def read(cls):
        path = gammacat_info.base_dir / 'input/papers'
        paths = sorted(path.glob('*/*/*.ecsv'))

        data = []
        for path in paths:
            sed = SED.read(path)
            data.append(sed)

        return cls(data=data)

    def validate(self):
        for sed in self.data:
            sed.process()

    def get_sed_by_source_id(self, source_id):
        missing = SED(table={}, path='')
        return self._sed_by_source_id.get(source_id, missing)
