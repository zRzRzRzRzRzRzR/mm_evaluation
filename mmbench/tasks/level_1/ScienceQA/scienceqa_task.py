import os
import json
import random
import pandas as pd
from io import BytesIO
from PIL import Image
from typing import Dict, List
from torch.utils.data import Dataset
from sat.helpers import print_rank0

from mmbench.common.registry import Registry
from mmbench.tasks.base_task import BaseTask

@Registry.register_task('ScienceQA')
class ScienceQA(BaseTask):
    def __init__(self, task_cfg, custom_functions, **kw_args):
        self.task_name = 'ScienceQA'
        self.ttypes = ["NO", "IMG", "TXT"]
        self.etypes = ["LAN", "NAT", "SOC", "G1-6", "G7-12"]
        self.img_pad = os.path.join(os.path.dirname(__file__), "no_img.png")
        super().__init__(task_cfg, custom_functions, **kw_args)
    
    def process_fn_webDataset(self, args, mt, src):
        for data in src:
            # img
            try:
                if 'jpg' in data:
                    img = Image.open(BytesIO(data['jpg'])).convert('RGB')
                else:
                    img = Image.open(self.img_pad).convert('RGB')
            except Exception as e:
                print_rank0(e)
                continue
            img_dict = {'vision': mt.image_processor(img)}
            if mt.cross_image_processor:
                img_dict.update({'cross': mt.cross_image_processor(img)})
            
            dialogues = json.loads(data['json'].decode("utf-8"))
            if args.data_mode == "train":
                dialogues = [random.choice(dialogues)]
            for qa in dialogues:
                ret = {
                    "question_id": qa["question_id"],
                    "label_text": qa["answer"]
                }
                # text
                prompt = qa["prompt"]
                if qa["ttype"] == "TXT":
                    context = qa["context"]
                    prompt = f"Context: {context}\n" + prompt
                text_dict = mt.text_processor(qa["answer"], prompt)
                if text_dict is None:
                    continue
                ret.update(text_dict)
                ret.update(img_dict)
                yield ret

    def calc_scores(self, args, results_total) -> Dict:
        """ Calculate scores with specified metrics.
          Args:
            @examples:
            @metrics:
          Return:
            A result dict keyed by metrics names.
        """
        mirror_df = self.get_data_mirror(args)

        metrics_scores = {}
        question_ids, preds, labels = results_total["question_ids"], results_total["preds"], results_total["labels"]
        res_df = pd.DataFrame({"question_ids": question_ids, "preds": preds, "labels": labels})
        # remove duplicates
        res_df = res_df.drop_duplicates(subset=["question_ids"])
        # compute scores
        metric_cls = Registry.get_metric_class('acc')
        metrics_scores["Avg"] = metric_cls.calc_scores(res_df["labels"], res_df["preds"])
        for ttype in self.ttypes: 
            c_df = mirror_df[mirror_df["ttype"] == ttype].drop_duplicates(subset=["question_id"])
            c_df = res_df[res_df["question_ids"].isin(c_df["question_id"])]
            metrics_scores[ttype] = metric_cls.calc_scores(c_df["labels"], c_df["preds"])
        # etypes
        img_df = mirror_df[mirror_df["ttype"] == "IMG"].drop_duplicates(subset=["question_id"])
        for etype in self.etypes:
            c_qids = [row["question_id"] for i, row in img_df.iterrows() if etype in row["etype"]]
            c_df = res_df[res_df["question_ids"].isin(set(c_qids))]
            metrics_scores[etype] = metric_cls.calc_scores(c_df["labels"], c_df["preds"])
        return metrics_scores
