import random, os
import numpy as np
import torch

from transformers import AutoTokenizer, AutoConfig, XLMRobertaAdapterModel
from datasets import load_dataset
from torch.utils.data import Dataset
import torch
import torch.nn.functional as F
from tqdm.notebook import tqdm
from torch import nn
import copy
from transformers import AdapterConfig
from datasets import load_dataset
from transformers import TrainingArguments
from transformers import DataCollatorForTokenClassification, DataCollatorWithPadding
from transformers import TrainingArguments, AdapterTrainer, EvalPrediction
from datasets import load_metric
import numpy as np
from transformers.adapters.composition import Stack
from torch.utils.data import DataLoader
from torch.optim import AdamW
from transformers import get_scheduler
from torch.utils.data import DataLoader
from tqdm.auto import tqdm
from my_utils.utils import *
from my_utils.config import *
from my_utils.logger import Logger
from my_utils.colors import bcolors

torch.cuda.empty_cache()
# torch.cuda.synchronize()

parser = get_arg_parser()
args = parser.parse_args()

seed = int(args.seed)
seed_everything(seed)

alpha = float(args.mean_l_alpha)

task = args.task.upper()

device = torch.device("cuda:"+args.gpu if torch.cuda.is_available() else "cpu")
device = torch.device("cpu")

if args.layers_c is not None:
    converter_active_layers = [int(s) for s in args.layers_c]

proj_active_layers = [int(s) for s in args.layers_p]
layer_probs = [float(p) for p in args.proj_prob]
mean_loss_layers = [int(l) for l in args.mean_loss]
#The labels for the NER task and the dictionaries to map the to ids or 
#the other way around
model_name = "xlm-roberta-base"

if len(args.src_lang) == 1:
  src_lang = args.src_lang[0]
else:
  src_lang = args.src_lang          

if len(args.target) == 1:
  tgt_lang = args.target[0]
else:
  tgt_lang = args.target

num_train_epochs = int(args.epochs)

# logger = Logger(p["logs_dir"] + "/" + model_name + "p_l_" + "_".join([str(i) for i in proj_active_layers]) + "_p_l_" + "_".join([str(pr) for pr in layer_probs]) +"_src_" + src_lang + "_tgt_" + tgt_lang + "_eps_" + str(num_train_epochs) + "_seed_" + str(seed) + ".log")
if args.baseline:
    logger = Logger(p["logs_dir"] + "/Proj2/" + model_name + "_src_" + src_lang + "_tgt_" + tgt_lang + "_eps_" + str(num_train_epochs) + "_seed_" + str(seed) + "_baseline.log")
else:
    logger = Logger(p["logs_dir"] + "/Proj2/" + model_name + "p_l_" + "|".join([str(i) + "_" + str(pr) + "_" + str(pl) for i,pr,pl in zip(proj_active_layers, args.proj_prob, args.policy)]) +"_src_" + src_lang + "_tgt_" + tgt_lang + "_eps_" + str(num_train_epochs) + "_seed_" + str(seed) + ".log")

logger.write("Seed: " + str(seed))

logger.draw_line()
logger.write("Loading model " + model_name, bcolors.OKCYAN)

tokenizer = AutoTokenizer.from_pretrained(model_name)

if args.train:

    if not args.checkpoint:
        config = AutoConfig.from_pretrained(model_name, num_labels=len(labels), label2id=label_2_id, id2label=id_2_label)
        model = XLMRobertaAdapterModel.from_pretrained(model_name, config=config)
        logger.write("Loading language adapters for: src - " + src_lang + " tgt - " + tgt_lang)
        lang_adapter_config = AdapterConfig.load("pfeiffer", reduction_factor=2)
        model.load_adapter(src_lang+"/wiki@ukp", config=lang_adapter_config) # leave_out=[11])
        model.load_adapter(tgt_lang+"/wiki@ukp", config=lang_adapter_config) # leave_out=[11])

        # model.add_converters(converter_active_layers)

        # Add a new task adapter
        logger.write("Loading task adapters")
        model.add_adapter("wikiann")
        logger.write("Loaded all adapters successfully!", bcolors.OKGREEN)

        if args.task.upper() == "NER":
            model.add_tagging_head("wikiann", num_labels=len(labels))
        elif args.task.upper() == "XNLI":
            model.add_classification_head("wikiann", num_labels=3)

    else:
        logger.write("Loading model from checkpoint")
        model = XLMRobertaAdapterModel.from_pretrained(args.checkpoint)

    model.train_adapter(["wikiann"])

    logger.write("Loading projections")
    model.load_adapter_projections([src_lang, tgt_lang], 0.9, './subspace/subspace_cache', device)
    logger.write("Loaded projections sucessfully!", bcolors.OKGREEN)

    # Load the language adapters
    if not args.checkpoint:
        optimizer = AdamW(model.parameters(), lr=1e-4)
    else:
        optimizer = torch.load(p["opt_dir"] + args.checkpoint[args.checkpoint.find("/")+1:])

elif args.test:
    config = AutoConfig.from_pretrained(model_name, num_labels=len(labels), label2id=label_2_id, id2label=id_2_label)
    # model = torch.load(args.test, config=config)
    model = XLMRobertaAdapterModel.from_pretrained(args.test)
    model.load_adapter_projections([src_lang, tgt_lang], 0.9, './subspace/subspace_cache', device)
    logger.write("Loaded model from " + args.test)
    best_model = model
else:
    print("Either train or test must be set to true")

logger.write("Loaded model " + model_name + " successfully!", bcolors.OKGREEN)

######################################################## XNLI

    # train_dataset = load_dataset(
    #     "xnli",
    #     src_lang,
    #     split="train",
    # )

    # train_label_list = train_dataset.features["label"].names

    # eval_dataset = load_dataset(
    #     "xnli",
    #     tgt_lang,
    #     split="validation",
    # )

    # eval_label_list = eval_dataset.features["label"].names

    # test_dataset = load_dataset(
    #     "xnli",
    #     tgt_lang,
    #     split="test",
    # )
    # test_label_list = test_dataset.features["label"].names

    # # Labels
    # num_labels = len(train_label_list)

    # padding = False

    # def preprocess_function(examples):
    #     # Tokenize the texts
    #     return tokenizer(
    #         examples["premise"],
    #         examples["hypothesis"],
    #         padding=padding,
    #         # max_length=data_args.max_seq_length,
    #         truncation=True,
    #     )

    # train_dataset = train_dataset.map(
    #     preprocess_function,
    #     batched=True,
    #     desc="Running tokenizer on train dataset",
    # )

    # eval_dataset = eval_dataset.map(
    #     preprocess_function,
    #     batched=True,
    #     desc="Running tokenizer on train dataset",
    # )

    # test_dataset = test_dataset.map(
    #     preprocess_function,
    #     batched=True,
    #     desc="Running tokenizer on train dataset",
    # )

    # Get the metric function
    # metric = evaluate.load("xnli")

    # # You can define your custom compute_metrics function. It takes an `EvalPrediction` object (a namedtuple with a
    # # predictions and label_ids field) and has to return a dictionary string to float.
    # def compute_metrics(p: EvalPrediction):
    #     preds = p.predictions[0] if isinstance(p.predictions, tuple) else p.predictions
    #     preds = np.argmax(preds, axis=1)
    #     return metric.compute(predictions=preds, references=p.label_ids)

    # Data collator will default to DataCollatorWithPadding, so we change it if we already did the padding.
    # if data_args.pad_to_max_length:
    #     data_collator = default_data_collator
    # elif training_args.fp16:
    #     data_collator = DataCollatorWithPadding(tokenizer, pad_to_multiple_of=8)
    # else:
    # data_collator = None
########################################################


logger.write("Loading and processing dataset", bcolors.OKCYAN)

# dataset_src = load_dataset('wikiann', src_lang)
# dataset_tgt = load_dataset('wikiann', tgt_lang)

# # # This method is adapted from the huggingface transformers run_ner.py example script
# # # Tokenize all texts and align the labels with them.

# def tokenize_and_align_labels(examples):
#     text_column_name = "tokens"
#     label_column_name = "ner_tags"
#     tokenized_inputs = tokenizer(
#         examples[text_column_name],
#         padding=False,
#         truncation=True,
#         # We use this argument because the texts in our dataset are lists of words (with a label for each word).
#         is_split_into_words=True,
#     )
#     labels = []
#     for i, label in enumerate(examples[label_column_name]):
#         word_ids = tokenized_inputs.word_ids(batch_index=i)
#         previous_word_idx = None
#         label_ids = []
#         for word_idx in word_ids:
#             # Special tokens have a word id that is None. We set the label to -100 so they are automatically
#             # ignored in the loss function.
#             if word_idx is None:
#                 label_ids.append(-100)
#             # We set the label for the first token of each word.
#             elif word_idx != previous_word_idx:
#                 label_ids.append(label[word_idx])
#             # For the other tokens in a word, we set the label to either the current label or -100, depending on
#             # the label_all_tokens flag.  
#             else:
#                 label_ids.append(-100)
#             previous_word_idx = word_idx

#         labels.append(label_ids)
#     tokenized_inputs["labels"] = labels
#     return tokenized_inputs

# dataset_src = dataset_src.map(
#     tokenize_and_align_labels,
#     batched=True,
#     remove_columns=dataset_src["train"].column_names,
# )
# dataset_tgt = dataset_tgt.map(
#     tokenize_and_align_labels,
#     batched=True,
#     remove_columns=dataset_tgt["train"].column_names,
# )

# data_collator = DataCollatorForTokenClassification(tokenizer,)

# train_dataloader = DataLoader(
#     dataset_src["train"],
#     shuffle=True,
#     collate_fn=data_collator,
#     batch_size=16,
# )
# eval_dataloader = DataLoader(
#     dataset_tgt["validation"], collate_fn=data_collator, batch_size=16
# )

# test_dataloader = DataLoader(
#     dataset_tgt["test"], collate_fn=data_collator, batch_size=16
# )

train_dataloader, eval_dataloader, test_dataloader = get_processed_dataset(task, tokenizer,src_lang, tgt_lang)

num_update_steps_per_epoch = len(train_dataloader)
num_training_steps = num_train_epochs * num_update_steps_per_epoch

if args.train:

    lr_scheduler = get_scheduler(
        "linear",
        optimizer=optimizer,
        num_warmup_steps=0,
        num_training_steps=num_training_steps,
    )

if task == "NER":
    metric = load_metric("seqeval")
elif task == "XNLI":
    # metric = evaluate.load("xnli")
    metric = load_metric("xnli")
# metric = load_metric(task)

logger.draw_line()
logger.write("Training started", bcolors.OKCYAN)

if args.train:

    frac_per_epoch = []
    progress_bar = tqdm(range(num_training_steps))

    best_model = None
    min_val_loss = 1e7

    model.to(device)

    model.disable_adapter_projection_stack()

    model.activate_mean_loss(mean_loss_layers)

    step = 0

    for i in range(12):
        model.set_proj_lang(i, tgt_lang)

    for layer in proj_active_layers:
        frac_per_epoch.append([])

    for epoch in range(num_train_epochs):

        # Unfreeze and activate stack setup
        model.active_adapters = Stack(src_lang, "wikiann")

        if not args.baseline:

            if args.layers_p is not None:
                for i, prob, policy in zip(proj_active_layers, layer_probs, args.policy):
                    model.activate_adapter_projection_stack('wikiann', i, tgt_lang, prob, policy, int(args.sig_center))

        val_loss = 0
        # Training
        model.train()

        for batch in train_dataloader:

            step += 1
            inputs = batch['input_ids'].to(device)
            labels = batch['labels'].to(device)
            outputs = model(input_ids=inputs, labels=labels)
            # loss = outputs.loss + alpha*model.get_mean_losses()
            loss = outputs.loss
            loss.backward()

            del labels
            del inputs

            optimizer.step()
            lr_scheduler.step()
            optimizer.zero_grad()
            progress_bar.update(1)

        for idx, layer in enumerate(proj_active_layers):
            frac = model.get_frac_count(layer)
            frac_per_epoch[idx].append(frac)

        model.eval()

        if not args.baseline:
            model.disable_adapter_projection_stack()
        model.active_adapters = Stack(tgt_lang, "wikiann")

        for batch in eval_dataloader:
            with torch.no_grad():
                inputs = batch['input_ids'].to(device)
                labels = batch['labels'].to(device)
                outputs = model(input_ids=inputs, labels=labels)
                val_loss += outputs.loss.item()

                del labels
                del inputs

                predictions = outputs.logits.argmax(dim=2)
                labels = batch["labels"]

                true_predictions, true_labels = postprocess(predictions, labels)
                metric.add_batch(predictions=true_predictions, references=true_labels)

        results = metric.compute()
        logger.draw_line()
        logger.write(">>> Epoch: " + str(epoch), bcolors.OKCYAN)
        logger.write(
        str(
            f"epoch {epoch}: " +
            str({
                key: results[f"overall_{key}"]
                for key in ["precision", "recall", "f1", "accuracy"]
            }),
        )
        )

        net_val_loss = val_loss/len(eval_dataloader)

        print(net_val_loss)

        test_loss = 0

        if not args.baseline:
            model.disable_adapter_projection_stack()

        model.active_adapters = Stack(tgt_lang, "wikiann")

        for batch in test_dataloader:
            with torch.no_grad():
                inputs = batch['input_ids'].to(device)
                labels = batch['labels'].to(device)
                outputs = model(input_ids=inputs, labels=labels)
                test_loss += outputs.loss.item()

            predictions = outputs.logits.argmax(dim=2)
            labels = batch["labels"]

                # Necessary to pad predictions and labels for being gathered
                #predictions = accelerator.pad_across_processes(predictions, dim=1, pad_index=-100)
                #labels = accelerator.pad_across_processes(labels, dim=1, pad_index=-100)

                #predictions_gathered = accelerator.gather(predictions)
                #labels_gathered = accelerator.gather(labels)

            true_predictions, true_labels = postprocess(predictions, labels)
            metric.add_batch(predictions=true_predictions, references=true_labels)

        results = metric.compute()
        # print(f"Testepoch {epoch}:", {key: results[f"overall_{key}"] for key in ["precision", "recall", "f1", "accuracy"]},)
        logger.write("Testepoch {epoch}:" + str({key: results[f"overall_{key}"] for key in ["precision", "recall", "f1", "accuracy"]}))
        logger.write(str(test_loss/len(test_dataloader)))

        # for layer in proj_active_layers:
        #     model.get_frac_count(layer)                 ## To empty the counts and fracs

        if min_val_loss > net_val_loss or best_model is None:
            best_model = model

            if args.baseline:
                if args.save:
                    best_model.save_pretrained(p["save_dir"] + "/" + model_name + "_src_" + src_lang + "_tgt_" + tgt_lang + "_eps_" + str(num_train_epochs) + "_seed_" + str(seed) + "_baseline.pt")
                    torch.save(optimizer, p["opt_dir"] + "/" + model_name + "_src_" + src_lang + "_tgt_" + tgt_lang + "_eps_" + str(num_train_epochs) + "_seed_" + str(seed) + "_baseline.pt")
            else:
                if args.save:
                    best_model.save_pretrained(p["save_dir"] + "/" + model_name + "p_l_" + "|".join([str(i) + "_" + str(pr) + "_" + str(pl) for i,pr,pl in zip(proj_active_layers, args.proj_prob, args.policy)])  + "_src_" + src_lang + "_tgt_" + tgt_lang + "_eps_" + str(num_train_epochs) + "_seed_" + str(seed) + "_".join(args.policy) + ".pt")
                    torch.save(optimizer, p["opt_dir"] + "/" + model_name + "p_l_" + "|".join([str(i) + "_" + str(pr) + "_" + str(pl) for i,pr,pl in zip(proj_active_layers, args.proj_prob, args.policy)])  + "_src_" + src_lang + "_tgt_" + tgt_lang + "_eps_" + str(num_train_epochs) + "_seed_" + str(seed) + "_".join(args.policy) + ".pt")
            min_val_loss = net_val_loss

    logger.draw_line()

    logger.write("Fraction of fractions for different epochs and layers:")
    logger.write("\t\t" + "\t".join([str(i) for i in proj_active_layers]))


    for epoch in range(num_train_epochs):
        logger.write("Epoch " + str(epoch + 1) + " : " + "\t".join([str(f[epoch]) for f in frac_per_epoch]))

if args.test:
    test_loss = 0
    best_model.to(device)
    best_model.disable_adapter_projection_stack()
    best_model.active_adapters = Stack(tgt_lang, "wikiann")
    epoch = "test"

    for batch in test_dataloader:
        with torch.no_grad():
            inputs = batch['input_ids'].to(device)
            labels = batch['labels'].to(device)
            outputs = best_model(input_ids=inputs, labels=labels)
            test_loss += outputs.loss.item()

        predictions = outputs.logits.argmax(dim=2)
        labels = batch["labels"]

        true_predictions, true_labels = postprocess(predictions, labels)
        metric.add_batch(predictions=true_predictions, references=true_labels)

    results = metric.compute()
    print(f"epoch {epoch}:", {key: results[f"overall_{key}"] for key in ["precision", "recall", "f1", "accuracy"]},)
    print(test_loss/len(test_dataloader))

logger.close()