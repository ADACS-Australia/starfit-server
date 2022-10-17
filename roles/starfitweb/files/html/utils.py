import base64
import os
import sys
import traceback
from datetime import datetime

import starfit
import yaml
from cerberus import Validator
from email_validator import EmailNotValidError, validate_email
from starfit.autils.human import time2human
from starfit.autils.isotope import ion as I
from starfit.read import Star

try:
    from starfit import __version__ as starfit_version
except ImportError:
    starfit_version = "unknown"


def convert_img_to_b64_tag(file, format):
    plot_b64 = str(base64.b64encode(file.getvalue()))[2:-1]
    typestr = format
    if format == "svg":
        typestr += "+xml"
    img_tag = f'<object data="data:image/{typestr};base64,{plot_b64}" type="image/{typestr}" width="700"></object>'

    return img_tag


class Config:
    schema = dict(
        email={"type": "string", "coerce": str},
        algorithm={"type": "string", "coerce": str},
        sol_size={"type": "integer", "coerce": int},
        z_min={"type": "integer", "coerce": int},
        z_max={"type": "integer", "coerce": int},
        combine_mode={"type": "integer", "coerce": int},
        pop_size={"type": "integer", "coerce": int},
        time_limit={"type": "integer", "coerce": int},
        database={"type": "string", "coerce": str},
        fixed={"type": "integer", "coerce": int},
        plotformat={"type": "string", "coerce": str},
        z_exclude={"type": "string", "coerce": str},
        z_lolim={"type": "string", "coerce": str},
        cdf={"type": "boolean", "coerce": bool},
    )

    def __init__(self, form):

        web_config = yaml.safe_load(open("config.yml"))

        try:
            stardata = form["stardata"]
        except:
            traceback.print_exc(file=sys.stderr)
            sys.exit()

        self.start_time = datetime.now().strftime("%Y-%M-%d-%H-%M-%S")

        v = Validator(require_all=True)

        conf = {}
        for key in self.schema:
            conf[key] = form.getfirst(key)

        if not v.validate(conf, self.schema):
            raise RuntimeError("Bad form input")

        for key, value in v.document.items():
            self.__setattr__(key, value)

        self.z_exclude = [
            z for z in [I(i).Z for i in self.z_exclude.split(",")] if z != 0
        ]
        self.z_lolim = [z for z in [I(i).Z for i in self.z_lolim.split(",")] if z != 0]

        # Save files to tmp
        if stardata.filename:
            filepath = os.path.join("/tmp", stardata.filename + self.start_time)
            with open(filepath, "wb") as fstar:
                fstar.write(stardata.file.read())
            filename = stardata.filename
        else:
            filename = "HE1327-2326.dat"
            filepath = os.path.join(starfit.DATA_DIR, "stars", filename)

        self.filepath = filepath
        self.filename = filename
        self.dbpath = os.path.join(web_config["db_dir"], self.database)
        self.mail = self.email != ""

        # Override time limit for some algorithms
        if self.algorithm == "double":
            self.time_limit = 60 * 15
        elif self.algorithm == "single":
            self.time_limit = 0

        if self.time_limit < 1:
            eta = "now"
        elif self.time_limit > 600:
            eta = "in more than 10 minutes"
        else:
            eta = "in " + time2human(self.time_limit)
        self.time_eta = eta

        if self.algorithm not in ("ga", "double", "single"):
            raise RuntimeError('Bad choice of "algorithm"')

        if self.algorithm == "double":
            self.sol_size = 2
        elif self.algorithm == "single":
            self.sol_size = 1

        # Check for errors after all the config has been handled
        self.errors = self._check_for_errors()

    def combine_elements(self):
        """Preset element combinations"""
        if self.combine_mode == 1:
            combine = [[6, 7]]
        elif self.combine_mode == 2:
            combine = [[6, 7, 8]]
        else:
            combine = [[]]

        return combine

    def combine_elements_str(self):
        group_strings = []
        for group in self.combine_elements():
            group_strings += ["+".join([I(i).element_symbol() for i in group])]
        output = ", ".join(group_strings)
        if output == "":
            output = "None"
        return output

    def get_algorithm_description(self):
        if self.algorithm == "ga":
            return "Genetic Algorithm (approximate best solution)"
        elif self.algorithm == "single":
            return "Complete search: single stars"
        elif self.algorithm == "double":
            return "Complete search: combinations of two stars"

    def _check_for_errors(self):
        errors = []
        try:
            Star(self.filename, silent=True)
        except:
            traceback.print_exc(file=sys.stderr)
            errors += ["There is something wrong with this stellar data."]

        # Test if the input parameters are any good
        if self.sol_size > 10:
            errors += ["Gene sizes greater than 10 are not supported."]

        if self.pop_size > 1000:
            errors += ["Population sizes over 1000 are not supported."]

        if self.time_limit > 60 and not self.mail:
            errors += ["Results must be emailed for time limit > 60s."]

        if self.mail:
            try:
                # Check that the email address is valid.
                validate_email(self.email, check_deliverability=True)

            except EmailNotValidError:
                traceback.print_exc(file=sys.stderr)
                errors += [f"{self.email} is not a valid email."]

        if self.plotformat == "pdf" and not self.mail:
            errors += ["PDF plot format must be emailed."]

        return errors

    def get_exc_string(self):
        exc_string = ", ".join([I(x).element_symbol() for x in self.z_exclude])
        if exc_string == "":
            exc_string = "None"
        return exc_string

    def get_lol_string(self):
        lol_string = ", ".join([I(x).element_symbol() for x in self.z_lolim])
        if lol_string == "":
            lol_string = "None"
        return lol_string


class JobInfo:
    def __init__(self, status=None, exc_info=None):
        self.status = status
        self.exc_info = exc_info
        self.starfit_version = starfit_version