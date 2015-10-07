from __future__ import print_function, division
from pyemu.la import LinearAnalysis

class Schur(LinearAnalysis):
    """derived type for posterior covariance analysis using Schur's complement
    """
    def __init__(self,jco,**kwargs):
        self.__posterior_prediction = None
        self.__posterior_parameter = None
        super(Schur,self).__init__(jco,**kwargs)


    def plot(self):
        raise NotImplementedError("need to do this!!!")


    @property
    def pandas(self):
        """get a pandas dataframe of prior and posterior for all predictions
        """
        names,prior,posterior = [],[],[]
        for iname,name in enumerate(self.posterior_parameter.row_names):
            names.append(name)
            posterior.append(np.sqrt(float(
                self.posterior_parameter[iname, iname]. x)))
            iprior = self.parcov.row_names.index(name)
            prior.append(np.sqrt(float(self.parcov[iprior, iprior].x)))
        for pred_name, pred_var in self.posterior_prediction.items():
            names.append(pred_name)
            posterior.append(np.sqrt(pred_var))
            prior.append(self.prior_prediction[pred_name])
        return pandas.DataFrame({"posterior": posterior, "prior": prior},
                                index=names)


    @property
    def posterior_parameter(self):
        """get the posterior parameter covariance matrix
        """
        if self.__posterior_parameter is not None:
            return self.__posterior_parameter
        else:
            self.clean()
            self.log("Schur's complement")
            self.__posterior_parameter = \
                ((self.jco.transpose * self.obscov ** (-1) *
                  self.jco) + self.parcov.inv).inv
            self.log("Schur's complement")
            return self.__posterior_parameter


    @property
    def posterior_forecast(self):
        return self.posterior_prediction

    @property
    def posterior_prediction(self):
        """get a dict of posterior prediction variances
        """
        if self.__posterior_prediction is not None:
            return self.__posterior_prediction
        else:
            if self.predictions is not None:
                self.log("propagating posterior to predictions")
                pred_dict = {}
                for prediction in self.predictions:
                    var = (prediction.T * self.posterior_parameter
                           * prediction).x[0, 0]
                    pred_dict[prediction.col_names[0]] = var
                self.__posterior_prediction = pred_dict
                self.log("propagating posterior to predictions")
            else:
                self.__posterior_prediction = {}
            return self.__posterior_prediction


    def get_parameter_summary(self):
        """get a summary of the parameter uncertainty
        Args:
            None
        Returns:
            pandas.DataFrame() of prior,posterior variances and percent
            uncertainty reduction of each parameter
        Raises:
            None
        """

        #ureduce = np.diag(100.0 * (1.0 - (self.posterior_parameter *
        #                                  (self.parcov**-1)).x))

        prior = self.parcov.get(self.posterior_parameter.col_names)
        if prior.isdiagonal:
            prior = prior.x.flatten()
        else:
            prior = np.diag(prior.x)
        post = np.diag(self.posterior_parameter.x)
        ureduce = 100.0 * (1.0 - (post / prior))
        return pandas.DataFrame({"prior_var":prior,"post_var":post,
                                 "percent_reduction":ureduce},
                                index=self.posterior_parameter.col_names)


    def get_forecast_summary(self):
        """get a summary of the forecast uncertainty
        Args:
            None
        Returns:
            pandas.DataFrame() of prior,posterior variances and percent
            uncertainty reduction of each forecast
        Raises:
            None
        """
        sum = {"prior_var":[], "post_var":[], "percent_reduction":[]}
        for forecast in self.prior_forecast.keys():
            pr = self.prior_forecast[forecast]
            pt = self.posterior_forecast[forecast]
            ur = 100.0 * (1.0 - (pt/pr))
            sum["prior_var"].append(pr)
            sum["post_var"].append(pt)
            sum["percent_reduction"].append(ur)
        return pandas.DataFrame(sum,index=self.prior_forecast.keys())

    def __contribution_from_parameters(self, parameter_names):
        """get the prior and posterior uncertainty reduction as a result of
        some parameter becoming perfectly known
        Args:
            parameter_names (list of str) : parameter that are perfectly known
        Returns:
            dict{prediction name : [prior uncertainty w/o parameter_names,
                % posterior uncertainty w/o parameter names]}
        Raises:
            Exception if no predictions are set
            Exception if one or more parameter_names are not in jco
            Exception if no parameter remain
        """
        if not isinstance(parameter_names, list):
            parameter_names = [parameter_names]

        for iname, name in enumerate(parameter_names):
            parameter_names[iname] = name.lower()
            assert name.lower() in self.jco.col_names,\
                "contribution parameter " + name + " not found jco"
        keep_names = []
        for name in self.jco.col_names:
            if name not in keep_names:
                keep_names.append(name)
        if len(keep_names) == 0:
            raise Exception("Schur.contribution_from_parameters: " +
                            "atleast one parameter must remain uncertain")
        #get the reduced predictions
        if self.predictions is None:
            raise Exception("Schur.contribution_from_parameters: " +
                            "no predictions have been set")
        cond_preds = []
        for pred in self.predictions:
            cond_preds.append(pred.get(keep_names, pred.col_names))
        la_cond = Schur(jco=self.jco.get(self.jco.row_names, keep_names),
                        parcov=self.parcov.condition_on(parameter_names),
                        obscov=self.obscov, predictions=cond_preds,verbose=False)

        #get the prior and posterior for the base case
        bprior,bpost = self.prior_prediction, self.posterior_prediction
        #get the prior and posterior for the conditioned case
        cprior,cpost = la_cond.prior_prediction, la_cond.posterior_prediction
        return cprior,cpost
        # pack the results into a dict{pred_name:[prior_%_reduction,
        # posterior_%_reduction]}
        #results = {}
        #for pname in bprior.keys():
            #prior_reduc = 100. * ((bprior[pname] - cprior[pname]) /
            #                      bprior[pname])
            #post_reduc = 100. * ((bpost[pname] - cpost[pname]) / bpost[pname])
            #results[pname] = [prior_reduc, post_reduc]
        #    results[pname] = [cprior[pname],cpost[pname]]
        #return results


    def get_contribution_dataframe(self,parlist_dict):
        """get a dataframe the prior and posterior uncertainty
        reduction as a result of
        some parameter becoming perfectly known
        Args:
            parlist_dict (dict of list of str) : groups of parameters
                that are to be treated as perfectly known.  key values become
                row labels in dataframe
        Returns:
            dataframe[parlist_dict.keys(),(forecast_name,<prior,post>)
                multiindex dataframe of Schur's complement results for each
                group of parameters in parlist_dict values.
        Raises:
            Exception if no predictions are set
            Exception if one or more parameter_names are not in jco
            Exception if no parameter remain
        """
        results = {}
        names = ["base"]
        for forecast in self.prior_forecast.keys():
            pr = self.prior_forecast[forecast]
            pt = self.posterior_forecast[forecast]
            reduce = 100.0 * ((pr - pt) / pr)
            results[(forecast,"prior")] = [pr]
            results[(forecast,"post")] = [pt]
            results[(forecast,"percent_reduce")] = [reduce]
        for case_name,par_list in parlist_dict.items():
            names.append(case_name)
            case_prior,case_post = self.__contribution_from_parameters(par_list)
            for forecast in case_prior.keys():
                pr = case_prior[forecast]
                pt = case_post[forecast]
                reduce = 100.0 * ((pr - pt) / pr)
                results[(forecast, "prior")].append(pr)
                results[(forecast, "post")].append(pt)
                results[(forecast, "percent_reduce")].append(reduce)

        df = pandas.DataFrame(results,index=names)
        return df


    def get_contribution_dataframe_groups(self):
        """get the forecast uncertainty contribution from each parameter
        group.  Just some sugar for get_contribution_dataframe
        """
        pargrp_dict = {}
        par = self.pst.parameter_data
        groups = par.groupby("pargp").groups
        for grp,idxs in groups.items():
            pargrp_dict[grp] = list(par.loc[idxs,"parnme"])
        return self.get_contribution_dataframe(pargrp_dict)


    def __importance_of_observations(self,observation_names):
        """get the importance of some observations for reducing the
        posterior uncertainty
        Args:
            observation_names (list of str) : observations to analyze
        Returns:
            dict{prediction_name:% posterior reduction}
        Raises:
            Exception if one or more names not in jco obs names
            Exception if all obs are in observation names
            Exception if predictions are not set
        """
        if not isinstance(observation_names, list):
            observation_names = [observation_names]
        for iname, name in enumerate(observation_names):
            observation_names[iname] = name.lower()
            if name.lower() not in self.jco.row_names:
                raise Exception("Schur.importance_of_observations: " +
                                "obs name not found in jco: " + name)
        keep_names = []
        for name in self.jco.row_names:
            if name not in observation_names:
                keep_names.append(name)
        if len(keep_names) == 0:
            raise Exception("Schur.importance_of_observations: " +
                            " atleast one observation must remain")
        if self.predictions is None:
            raise Exception("Schur.importance_of_observations: " +
                            "no predictions have been set")

        la_reduced = self.get(par_names=self.jco.col_names,
                              obs_names=keep_names)
        return la_reduced.posterior_prediction
        #rpost = la_reduced.posterior_prediction
        #bpost = self.posterior_prediction

        #results = {}
        #for pname in rpost.keys():
        #    post_reduc = 100. * ((rpost[pname] - bpost[pname]) / rpost[pname])
        #    results[pname] = post_reduc
        #return results


    def get_importance_dataframe(self,obslist_dict=None):
        """get a dataframe the posterior uncertainty
        as a result of losing some observations
        Args:
            obslist_dict (dict of list of str) : groups of observations
                that are to be treated as lost.  key values become
                row labels in dataframe. If None, then test every obs
        Returns:
            dataframe[obslist_dict.keys(),(forecast_name,post)
                multiindex dataframe of Schur's complement results for each
                group of observations in obslist_dict values.
        """
        if obslist_dict is None:
            obs = self.pst.observation_data.loc[:,["obsnme","weight"]]
            obslist_dict = {}
            for o, w in zip(obs.obsnme,obs.weight):
                if w > 0:
                    obslist_dict[o] = [o]

        results = {}
        names = ["base"]
        for forecast,pt in self.posterior_forecast.items():
            results[forecast] = [pt]
        for case_name,obs_list in obslist_dict.items():
            names.append(case_name)
            case_post = self.__importance_of_observations(obs_list)
            for forecast,pt in case_post.items():
                results[forecast].append(pt)
        df = pandas.DataFrame(results,index=names)
        return df


    def get_importance_dataframe_groups(self):
        obsgrp_dict = {}
        obs = self.pst.observation_data
        obs.index = obs.obsnme
        obs = obs.loc[self.jco.row_names,:]
        groups = obs.groupby("obgnme").groups
        for grp, idxs in groups.items():
            obsgrp_dict[grp] = list(obs.loc[idxs,"obsnme"])
        return self.get_importance_dataframe(obsgrp_dict)

    @staticmethod
    def test():
        #non-pest
        pnames = ["p1","p2","p3"]
        onames = ["o1","o2","o3","o4"]
        npar = len(pnames)
        nobs = len(onames)
        j_arr = np.random.random((nobs,npar))
        jco = Matrix(x=j_arr,row_names=onames,col_names=pnames)
        parcov = Cov(x=np.eye(npar),names=pnames)
        obscov = Cov(x=np.eye(nobs),names=onames)
        forecasts = "o2"

        s = Schur(jco=jco,parcov=parcov,obscov=obscov,forecasts=forecasts)
        print(s.get_parameter_summary())
        print(s.get_forecast_summary())


        #this should fail
        try:
            print(s.get_contribution_dataframe_groups())
        except Exception as e:
            print(str(e))

        #this should fail
        try:
            print(s.get_importance_dataframe_groups())
        except Exception as e:
            print(str(e))

        print(s.get_contribution_dataframe({"group1":["p1","p3"]}))

        print(s.get_importance_dataframe({"group1":["o1","o3"]}))



